from configparser import (
    RawConfigParser,
    SectionProxy,

    Error,
    ParsingError,
    NoOptionError,
    NoSectionError,
    InterpolationError,
    DuplicateOptionError,
    DuplicateSectionError,
    InterpolationDepthError,
    InterpolationSyntaxError,
    MissingSectionHeaderError,
    InterpolationMissingOptionError,

    _default_dict,
    DEFAULTSECT,
    _UNSET
)
from collections import ChainMap, defaultdict, deque
from .composemap import ComposeMutMap
import functools
import itertools
from typing import Any, TextIO
import sys
import re
import warnings

class SectionInheritanceError(Error): ...

class Lekvar(RawConfigParser):
    _SECT_TMPL = r"""
        \[                          # ex.: [ q.w.e.asd : b,c,d]
        (?P<header>                 # header: ' q.w.e.asd '
        ((?P<base>[^:]+)\.)?        # base: ' q.w.e'
        (?P<head>[^:\.]+)           # head: 'asd '
        )
        (:(?P<inherit>.*))?         # inherit: ' b,c,d'
        \]
        """
    _OPT_TMPL = r"""                # ex.: ' a > b = 123'
        (?P<option>.*?)             # option: ' a'
        (\s*>\s*
        (?P<to_head>[^{delim}]+)    # to_head: 'b ' 
        )?
        \s*(?P<vi>{delim})\s*       # vi: '=' 
        (?P<value>.*)$              # value: '123'
        """
    # _OPT_NV_TMPL = r""" # TODO

    SECTCRE = re.compile(_SECT_TMPL, re.VERBOSE)
    OPTCRE = re.compile(_OPT_TMPL.format(delim="=|:"), re.VERBOSE)
    # OPTCRE_NV = re.compile(_OPT_NV_TMPL.format(delim="=|:"), re.VERBOSE)
    NONSPACECRE = re.compile(r"\S")
    BOOLEAN_STATES = {'1': True, 'yes': True, 'true': True, 'on': True,
                      '0': False, 'no': False, 'false': False, 'off': False}
    
    def __init__(self, defaults=None, dict_type=_default_dict,
                 allow_no_value=False, *, delimiters=('=', ':'),
                 comment_prefixes=('#', ';'), inline_comment_prefixes=None,
                 strict=True, empty_lines_in_values=True,
                 default_section=DEFAULTSECT,
                 interpolation=_UNSET, converters=_UNSET):
        
        super().__init__(
            defaults, dict_type, allow_no_value, 
            delimiters = delimiters,
            comment_prefixes = comment_prefixes, 
            inline_comment_prefixes = inline_comment_prefixes,
            strict = strict, 
            empty_lines_in_values = empty_lines_in_values,
            default_section = default_section,
            interpolation = interpolation, 
            converters = converters)
        # TODO: maybe should just initialize it myself
        
        self._all_options = self._dict()
        self._defaults: ComposeMutMap = ComposeMutMap(self._dict(), self._all_options)
        self._sections: dict[str, ComposeMutMap] = self._dict()

        self._proxy_tree: dict[str, str] = self._dict()
        self._proxy_inheritance: dict[str, deque] = self._dict()
        
        self._inherit_fw = self._dict()
    
    def _resolve_inline_inheritance(self):
        to_be_created = defaultdict(dict)

        for section_name, section_dict in self._sections.items():
            to_be_deleted = list()
            for temp, val in section_dict.items():
                if ">" not in temp: continue

                key, subsec_name = temp.split(">")
                key = key.strip()
                subsec_name = subsec_name.strip()

                sec = f"{section_name}.{subsec_name}"
                to_be_created[sec][key] = val
                to_be_deleted.append(temp)
            
            for key in to_be_deleted:
                del self._sections[section_name][key]
        
        for section_name, new_section_dict in to_be_created.items():
            if section_name not in self._sections.keys():
                self.add_section(section_name)
            
            section_dict = self._sections[section_name]
            self._sections[section_name] = {**new_section_dict, **section_dict}
    
    def _resolve_section_names(self):
        to_be_deleted = []
        new_sections = dict()
        new_proxies = dict()
        new_inh = set()

        # TODO: update while iterating through it
        for temp in self._sections.keys():
            if ":" not in temp: 
                self._proxy_inheritance[temp] = [temp]
                continue
                
            section, inheritance = temp.split(":")
            section = section.strip()
            inheritance = [sec.strip() for sec in inheritance.split(",")]
            new_inh.update(inheritance)

            self._proxy_inheritance[section] = [section] + inheritance

            new_sections[section] = self._sections[temp]
            new_proxies[section] = self._proxies[temp]
            new_proxies[section]._name = section
            to_be_deleted.append(temp)

        for sec in to_be_deleted:
            del self._sections[sec]
            del self._proxies[sec]

        self._sections.update(new_sections)
        self._proxies.update(new_proxies)
        print(new_inh)
        for sec in new_inh:
            if sec in self._sections.keys(): continue
            self.add_section(sec)

    def add_section(self, section):
        if section == self.default_section:
            raise ValueError('Invalid section name: %r' % section)

        if section in self._sections:
            raise DuplicateSectionError(section)
        self._sections[section] = ComposeMutMap(self._dict(), self._all_options)
        self._proxies[section] = SectionProxy(self, section)

    def options(self, section):
        try:
            opts = self._sections[section]
        except KeyError:
            raise NoSectionError(section) from None
        return list(opts.keys())

    def get(self, section, option, *, raw=False, vars=None, fallback=_UNSET):
        if section == self.default_section:
            section_dict = self._defaults
        else: 
            try:
                section_dict = self._sections[section]
            except KeyError:
                if fallback is _UNSET:
                    raise NoSectionError(section)
                else:
                    return fallback
        
        try: 
            value = section_dict[option]
        except KeyError:
            if fallback is _UNSET:
                raise NoOptionError(option, section)
            else: 
                return fallback
        
        if raw or value is None:
            return value
        else: 
            # TODO: Interpolation
            return value

    def items(self, section=_UNSET, raw=False, vars=None):
        if section is _UNSET: 
            return super().items()
        # TODO: everything else
        #return super().items(section, raw, vars)

    def popitem(self):
        # TODO: only the leafs should be able to pop
        return super().popitem()
    
    def set(self, section, option, value=None, in_read = False):
        # TODO: interpolation
                
        if not section or section == self.default_section:
            sectdict = self._defaults
            section = ''
        else:
            try:
                sectdict = self._sections[section]
            except KeyError:
                raise NoSectionError(section) from None
        
        rel_opt = self.optionxform(option.strip())
        abs_opt = f"{section}.{rel_opt}"

        sectdict.dict_1[rel_opt] = abs_opt
        if value == None:
            sectdict.dict_2[abs_opt] = None
        else:
            sectdict.dict_2[abs_opt] = value if not in_read else [value]
        
    def write(self, fp, space_around_delimiters=True):
        # TODO: writing is tricky
        raise NotImplementedError
        return super().write(fp, space_around_delimiters)
    
    def remove_option(self, section, option):
        # TODO: DAG
        raise NotImplementedError
        return super().remove_option(section, option)

    def remove_section(self, section):
        # TODO: DAG
        raise NotImplementedError
        return super().remove_section(section)
    
    def __setitem__(self, key, value):
        raise NotImplementedError
    
    def __delitem__(self, key):
        raise NotImplementedError

    def __len__(self):
        # TODO: what is the logical length, when we account for inheritance?
        return super().__len__()


    def _read(self, fp: TextIO, fpname: str):
        elements_added = set()
        curproxy: SectionProxy | None = None                        # None, or a dictionary
        sectname = None
        to_sect = None
        optname = None
        lineno = 0
        indent_level = 0
        e: Exception | None = None
        for lineno, line in enumerate(fp, start=1):
            comment_start = sys.maxsize
            # strip inline comments
            # TODO: interesting logic, might rewrite, regexify
            inline_prefixes = {p: -1 for p in self._inline_comment_prefixes}
            while comment_start == sys.maxsize and inline_prefixes:
                next_prefixes = {}
                for prefix, index in inline_prefixes.items():
                    index = line.find(prefix, index+1)
                    if index == -1:
                        continue
                    next_prefixes[prefix] = index
                    if index == 0 or (index > 0 and line[index-1].isspace()):
                        comment_start = min(comment_start, index)
                inline_prefixes = next_prefixes
            # strip full line comments
            for prefix in self._comment_prefixes:
                if line.strip().startswith(prefix):
                    comment_start = 0
                    break
            if comment_start == sys.maxsize:
                comment_start = None
            value = line[:comment_start].strip()
            if not value:
                if self._empty_lines_in_values:
                    # add empty line to the value, but only if there was no
                    # comment on the line
                    if (comment_start is None and
                        curproxy is not None and
                        optname and
                        self._all_options[f"{to_sect}.{optname}"] is not None):
                        self._all_options[f"{to_sect}.{optname}"].append('') # newlines added at join
                else:
                    # empty line marks end of value
                    indent_level = sys.maxsize
                continue
            # continuation line?
            first_nonspace = self.NONSPACECRE.search(line)
            cur_indent_level = first_nonspace.start() if first_nonspace else 0
            if (curproxy is not None and optname and
                cur_indent_level > indent_level):
                self._all_options[f"{to_sect}.{optname}"].append(value)
            # a section header or option header?
            else:
                indent_level = cur_indent_level
                # is it a section header?
                mo = self.SECTCRE.match(value)
                if mo:
                    header, base, head, inherit = mo.group('header', 'base', 'head', 'inherit')
                    header = header.strip()
                    if header == self.default_section:
                        curproxy = self._proxies[self.default_section]
                        sectname = ''
                        if inherit != None: 
                            raise SectionInheritanceError("Default section cannot inherit.")
                    else: 
                        sectname = header
                        self.add_section(sectname)
                        curproxy = self._proxies[sectname]
                        elements_added.add(sectname)
                    # So sections can't start with a continuation line
                    optname = None
                # no section header in the file?
                elif sectname is None:
                    raise MissingSectionHeaderError(fpname, lineno, line)
                # an option line?
                else:
                    mo = self._optcre.match(value)
                    if mo:
                        optname, to_head, vi, optval = mo.group('option', 'to_head', 'vi', 'value')
                        if not optname:
                            e = self._handle_error(e, fpname, lineno, line)
                        if to_head is not None:
                            to_sect = f"{sectname}.{to_head.strip()}"
                            if to_sect not in self._sections:
                                self.add_section(to_sect)
                        else: 
                            to_sect = sectname
                        optname = self.optionxform(optname.rstrip())
                        if (self._strict and
                            (to_sect, optname) in elements_added):
                            raise DuplicateOptionError(to_sect, optname,
                                                       fpname, lineno)
                        elements_added.add((to_sect, optname))
                        self.set(to_sect, optname, optval, True)
                        # TODO: value type parsing
                    else:
                        # a non-fatal parsing error occurred. set up the
                        # exception but keep going. the exception will be
                        # raised at the end of the file and will contain a
                        # list of all bogus lines
                        e = self._handle_error(e, fpname, lineno, line)
        self._join_multiline_values()
        # if any parsing errors occurred, raise an exception
        if e:
            raise e


    def _join_multiline_values(self):
        for name, val in self._all_options.items():
            if isinstance(val, list):
                val = '\n'.join(val).rstrip()
                self._all_options[name] = val
            # TODO: interpolation
            # self._all_options[name] = self._interpolation.before_read(self, section, name, val)

    def _unify_values(self, section, vars):
        warnings.warn("Under normal operaion of 'Lekvar', this is never called.")
        return super()._unify_values(section, vars)