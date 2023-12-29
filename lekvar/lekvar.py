from configparser import RawConfigParser, NoSectionError, _default_dict
from configparser import DuplicateSectionError, DuplicateOptionError, MissingSectionHeaderError
from collections import ChainMap, defaultdict, deque
from collections.abc import MutableMapping
import functools
from typing import Any, TextIO
import sys
import re

class LekvarParameter:
    def __init__(self, name, value):
        self._name: str = name
        self._value = value
        self._locations = deque()

    def __str__(self):
        return self._value.__str__()
    
    def __repr__(self):
        return self._value.__repr__()

class LekvarSectionProxy(MutableMapping):
    def __init__(self, parser, name):
        self._parser: Lekvar = parser
        self._name = name
        for conv in parser.converters:
            key = 'get' + conv
            getter = functools.partial(self.get, _impl=getattr(parser, key))
            setattr(self, key, getter)
        self._option_references: _default_dict[str, str] = _default_dict()
        self._inherit_bw: deque[LekvarSectionProxy] = deque()
        self._inherit_fw: deque[LekvarSectionProxy] = deque()


    def __repr__(self):
        return '<Section: {}>'.format(self._name)

    def __getitem__(self, key):
        if not self._parser.has_option(self._name, key):
            raise KeyError(key)
        return self._parser.get(self._name, key)

    def __setitem__(self, key, value):
        self._parser._validate_value_types(option=key, value=value)
        return self._parser.set(self._name, key, value)

    def __delitem__(self, key):
        if not (self._parser.has_option(self._name, key) and
                self._parser.remove_option(self._name, key)):
            raise KeyError(key)

    def __contains__(self, key):
        return self._parser.has_option(self._name, key)

    def __len__(self):
        return len(self._options())

    def __iter__(self):
        return self._options().__iter__()
    
    def _options(self):
        if self._name != self._parser.default_section:
            return self._parser.options(self._name)
        else:
            return self._parser.defaults()

    @property
    def parser(self):
        # The parser object of the proxy is read-only.
        return self._parser

    @property
    def name(self):
        # The name of the section on a proxy is read-only.
        return self._name

    def get(self, option, fallback=None, *, raw=False, vars=None,
            _impl=None, **kwargs):
        """Get an option value.

        Unless `fallback` is provided, `None` will be returned if the option
        is not found.

        """
        # If `_impl` is provided, it should be a getter method on the parser
        # object that provides the desired type conversion.
        if not _impl:
            _impl = self._parser.get
        return _impl(self._name, option, raw=raw, vars=vars,
                     fallback=fallback, **kwargs)

class Lekvar(RawConfigParser):
    r"\[((?P<head>[^:]+)\.)?(?P<main>[^:.]+)(\s*:\s*(?P<inh>.*)\s*)?\]"
    _SECT_TMPL = r"""
        \[                          # ex.: [ q.w.e.asd : b,c,d]
        (?P<header>                 # header: ' q.w.e.asd '
        ((?P<base>[^:]+)\.)?        # base: ' q.w.e'
        (?P<head>[^:\.]+)           # head: 'asd '
        )
        (:(?P<inherit>.*))?         # inherit: ' b,c,d'
        \]
        """
    _OPT_TMPL = r"""                    # ex.: ' a > b = 123'
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
    
    def __init__(self): 
        super().__init__()
        self._proxy_tree: _default_dict[str, str] = _default_dict()
        self._proxy_inheritance: _default_dict[str, deque] = _default_dict()
        self._param_dict = _default_dict()
        self._all_options = _default_dict()

    def __getitem__(self, __name: str) -> Any:
        if __name == self.default_section:
            return self._defaults.copy()
        if __name not in self._sections.keys(): 
            raise KeyError
        
        # TODO: this doesnt work with yet
        # TODO: probably has a lot of bugs
        final = self._defaults.copy()
        for name in self._proxy_inheritance[__name]:
            current = name
            while current != self.default_section:
                #print("Getting tags for ", ".".join(tags[:i+1]))
                final = {**self._sections[current], **final}
                current = self._proxy_tree[current]
        return final
    
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

    
    def _unify_values(self, section, vars):
        map_order = []
        current = section
        try: 
            while current != self.default_section:
                map_order.append(self._sections[current])
                current = self._proxy_tree[current]
        except KeyError:
            if section != self.default_section:
                raise NoSectionError(section) from None
        vardict = {}
        if vars:
            for key, value in vars.items():
                if value is not None:
                    value = str(value)
                vardict[self.optionxform(key)] = value
        return ChainMap(vardict, *map_order, self._defaults)
    
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


    def options(self, section):
        opts = dict()
        current = section
        try:
            while current != self.default_section:
                opts = {**self._sections[current], **opts}
                current = self._proxy_tree[current]
        except KeyError:
            raise NoSectionError(section) from None
        opts = {**self._defaults, **opts}
        return list(opts.keys())
    
    def has_option(self, section: str, option: str) -> bool:
        if not section or section == self.default_section:
            option = self.optionxform(option)
            return option in self._defaults
        elif section not in self._sections:
            return False
        else:
            option = self.optionxform(option)
            return option in self.options(section)
        
    def add_section(self, section):
        if section == self.default_section:
            raise ValueError('Invalid section name: %r' % section)

        if section in self._sections:
            raise DuplicateSectionError(section)
        self._sections[section] = self._dict()
        self._proxies[section] = LekvarSectionProxy(self, section)
        
    def _read(self, fp: TextIO, fpname: str):
        elements_added = set()
        cursect = None                        # None, or a dictionary
        sectname = None
        optname = None
        lineno = 0
        indent_level = 0
        e: Exception | None = None
        for lineno, line in enumerate(fp, start=1):
            comment_start = sys.maxsize
            # strip inline comments
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
                        cursect is not None and
                        optname and
                        cursect[optname] is not None):
                        cursect[optname].append('') # newlines added at join
                else:
                    # empty line marks end of value
                    indent_level = sys.maxsize
                continue
            # continuation line?
            first_nonspace = self.NONSPACECRE.search(line)
            cur_indent_level = first_nonspace.start() if first_nonspace else 0
            if (cursect is not None and optname and
                cur_indent_level > indent_level):
                cursect[optname].append(value)
            # a section header or option header?
            else:
                indent_level = cur_indent_level
                # is it a section header?
                mo = self.SECTCRE.match(value)
                if mo:
                    sectname = mo.group('header')
                    if sectname == self.default_section:
                        cursect = self._defaults
                    else: 
                        self.add_section(sectname)
                        cursect = self._sections[sectname]
                        elements_added.add(sectname)
                    # So sections can't start with a continuation line
                    optname = None
                # no section header in the file?
                elif cursect is None:
                    raise MissingSectionHeaderError(fpname, lineno, line)
                # an option line?
                else:
                    mo = self._optcre.match(value)
                    if mo:
                        optname, vi, optval = mo.group('option', 'vi', 'value')
                        if not optname:
                            e = self._handle_error(e, fpname, lineno, line)
                        optname = self.optionxform(optname.rstrip())
                        if (self._strict and
                            (sectname, optname) in elements_added):
                            raise DuplicateOptionError(sectname, optname,
                                                       fpname, lineno)
                        elements_added.add((sectname, optname))
                        if optval is not None:
                            optval = optval.strip()
                            cursect[optname] = [optval]
                            # TODO: value type parsing
                        else:
                            cursect[optname] = None
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
