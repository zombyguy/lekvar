from configparser import RawConfigParser, NoSectionError, SectionProxy, _default_dict
from configparser import DuplicateSectionError, DuplicateOptionError, MissingSectionHeaderError
from collections import ChainMap, defaultdict, deque
from typing import Any
import sys

class Lekvar(RawConfigParser):
    
    def __init__(self): 
        super().__init__()
        self._proxy_tree = _default_dict()
        self._proxy_inheritance = _default_dict()
        self._param_dict = _default_dict()

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
            

    def _build_tree(self):
        self._proxy_tree = {self.default_section: None}
        for name in self._proxies.keys():
            self._assign_parent_proxy(name)

    def _assign_parent_proxy(self, name):
        if name in self._proxy_tree.keys(): return

        i = name.rfind(".")
        if i == -1: self._proxy_tree[name] = self.default_section; return
        
        parent = name[:i]
        self._proxy_tree[name] = parent
        if parent not in self._proxies.keys():
            self.add_section(parent)
            self._assign_parent_proxy(parent)
    
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