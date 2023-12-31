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
from collections.abc import ItemsView
from .composemap import ComposeMutMap
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

    _INCL_TMPL = r"""
        INCLUDE\s+
        (?P<option>(?P<base>.*\.)(?P<head>[^.\s]+))
        (\s+AS\s+(?P<rename>.*))?
        """

    _REN_TMPL = r"""
        RENAME\s+
        (?P<option>.*)
        \s+TO\s+
        (?P<rename>.*)
        """

    _AVD_TMPL = r"""
        AVOID\s+
        (?P<option>.*)
        """
    
    _ONLY_TMPL = r"""
        ONLY\s+
        (?P<options>.*)
        """

    SECTCRE = re.compile(_SECT_TMPL, re.VERBOSE)
    OPTCRE  = re.compile(_OPT_TMPL.format(delim="=|:"), re.VERBOSE)
    INCLCRE = re.compile(_INCL_TMPL, re.VERBOSE)
    RENCRE  = re.compile(_REN_TMPL , re.VERBOSE)
    AVDCRE  = re.compile(_AVD_TMPL , re.VERBOSE)
    ONLYCRE = re.compile(_ONLY_TMPL, re.VERBOSE)
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
        
        self._inherit_fw: dict[str, deque[str]] = defaultdict(deque)
        self._inherit_bw: dict[str, deque[str]] = defaultdict(deque)
        self._top_order: list[str]

        self._renames: dict[str, dict[str,str]] = defaultdict(lambda: defaultdict(str))
        self._avoids: dict[str, deque[str]] = defaultdict(deque)
        self._only: dict[str, set[str]] = defaultdict(set)

    def _create_topological_order(self):
        source_que = deque()
        source_que.append("DEFAULT")
        in_degrees = {sect: len(inh) for sect, inh in self._inherit_bw.items()}
        top_order = list()

        while len(source_que) > 0:
            source = source_que.popleft()
            top_order.append(source)
            
            for out_nb in self._inherit_fw[source]:
                in_degrees[out_nb] -= 1
                if in_degrees[out_nb] == 0: 
                    source_que.append(out_nb)
        
        self._top_order = top_order

    def _resolve_inheritance_dag(self):
        self._create_topological_order()
        
        for section in self._top_order[1:]:
            for in_nb in self._inherit_bw[section]:
                if in_nb == self.default_section:
                    in_sec = self._defaults
                else: 
                    in_sec = self._sections[in_nb]
                for option in self._options(in_nb):
                    if option in self._options(section):
                        continue
                    self._sections[section].dict_1[option] = \
                        in_sec.dict_1[option]
            
            for opt, new_opt in self._renames[section].items():
                self._sections[section].dict_1[new_opt] = self._sections[section].dict_1[opt]
                del self._sections[section].dict_1[opt]

            for opt in self._avoids[section]:
                self._sections[section].dict_1.pop(opt, None)

            if section in self._only:
                sect_dict = self._sections[section].dict_1
                for opt in list(sect_dict.keys()):
                    if opt not in self._only[section]:
                        del sect_dict[opt]


    def add_section(self, section: str):
        if section == self.default_section:
            raise ValueError('Invalid section name: %r' % section)

        if section in self._sections:
            raise DuplicateSectionError(section)

        self._sections[section] = ComposeMutMap(self._dict(), self._all_options)
        self._proxies[section] = SectionProxy(self, section)

        self._inherit_fw[section] # initializes it
        if (i := section.rfind(".")) == -1:
            self._inherit_bw[section].appendleft(self.default_section)
            self._inherit_fw[self.default_section].append(section)
        else:
            head = section[:i]
            if head not in self._sections:
                self.add_section(head)
            self._inherit_bw[section].appendleft(head)
            self._inherit_fw[head].append(section)

    def options(self, section):
        return list(self._options(section))

    def _options(self, section):
        if section == self.default_section:
            return self._defaults.keys()

        try:
            opts = self._sections[section]
        except KeyError:
            raise NoSectionError(section) from None
        return opts.keys()

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

    def items(self, section:str =_UNSET, raw=False, vars=None) -> list | ItemsView:
        if section is _UNSET: 
            return super().items()
        
        try:
            d = dict(self._sections[section])
        except KeyError:
            if section != self.default_section:
                raise NoSectionError(section)
            else:
                d = dict(self._defaults)
        
        if vars:
            for key, value in vars.items():
                k = self.optionxform(key)
                if k in d:
                    d[self.optionxform(key)] = value

        #TODO: interpolation
        if raw:
            value_getter = lambda option: d[option]
        else: 
            value_getter = lambda option: self._interpolation.before_get(self,
                section, option, d[option], d)
        return [(option, value_getter(option)) for option in d.keys()]

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
        curproxy: SectionProxy | None = None
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
                if mo := self.SECTCRE.match(value):
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

                        if inherit is not None:
                            inherit_from = [i.strip() for i in inherit.split(",")]
                            for inh in inherit_from:
                                self._inherit_bw[header].append(inh)
                                self._inherit_fw[inh].append(header)

                    # So sections can't start with a continuation line
                    optname = None
                # no section header in the file?
                elif sectname is None:
                    raise MissingSectionHeaderError(fpname, lineno, line)
                # an option line?
                elif mo := self._optcre.match(value):
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

                elif mo := self.INCLCRE.match(value):
                    if not (opt_name := mo.group("rename")):
                        opt_name = mo.group("head")
                        
                    self._sections[sectname].dict_1[opt_name] = mo.group("option")

                elif mo := self.RENCRE.match(value):
                    self._renames[sectname][mo.group("option")] = mo.group("rename")
                
                elif mo := self.AVDCRE.match(value):
                    self._avoids[sectname].append(mo.group("option"))

                elif mo := self.ONLYCRE.match(value):
                    for opt in mo.group("options").split(","):
                        opt = opt.strip()
                        self._only[sectname].add(opt)
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