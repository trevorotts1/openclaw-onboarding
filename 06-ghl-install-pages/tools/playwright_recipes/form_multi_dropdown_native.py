"""Captured Multi Dropdown descriptor sharing the measured choice-row controls.

Unlike Single Dropdown, native Multi Dropdown has no local Query Key control;
its immutable Advanced canonical contact Unique Key owns the field identity.
"""
from playwright_recipes.form_single_dropdown_native import PROPERTIES, validate_properties, read_options, write_options

PROFILE={'type':'MULTIPLE_OPTIONS','tile':'Multi Dropdown','suffix':4,
         'key_prefix':'multi_dropdown_','key_property':'unique_key',
         'properties':{key:selector for key,selector in PROPERTIES.items() if key!='query_key'},
         'flags':{'required':'#fieldRequired'},'input':'input.dropdown-input',
         'extra':('options','calculations'),
         'defaults':{'placeholder':'Choose one or more options','short_label':'','width':100,
                     'required':False,'options':[{'label':'Option '+str(i),'value':None} for i in (1,2,3)],
                     'calculations':False}}
