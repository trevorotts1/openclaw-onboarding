import unittest
import checkout_ui as ui
from pages_checkout import CheckoutRefused

class Control:
    def __init__(self, item): self.item,self.value,self.pressed,self.visible=item,'old','false',True
    def count(self): return 1
    def is_visible(self): return self.visible
    def wait_for(self, **kwargs):
        if not self.visible: raise CheckoutRefused('control absent')
    def bounding_box(self): return {'x':1,'y':1,'width':20,'height':20} if self.visible else None
    def get_attribute(self, name): return self.pressed if name == 'aria-pressed' else None
    def input_value(self): return self.value
    def fill(self, value): self.value = value
    def select_option(self, value): self.value = value
    def click(self): self.pressed = 'true'
    def and_(self, by_id): return self if by_id == self.item['id'] else Missing()
class Missing:
    def count(self): return 0
    def is_visible(self): return False
    def wait_for(self, **kwargs): raise CheckoutRefused('control absent')
class Panel:
    def __init__(self, profile): self.controls={i['id']:Control(i) for i in profile}
    def get_by_role(self, role, name, exact):
        if role == 'button' and name == 'Theme & style': return Control({'id':'nav'})
        matches=[c for c in self.controls.values() if c.item['role']==role and c.item['name']==name]
        return matches[0] if len(matches)==1 else Missing()
    def locator(self, selector):
        import json
        return json.loads(selector[len('[id='):-1])
    def get_by_text(self, *args, **kwargs): return Missing()
def profile():
    b={'x':1,'y':2,'width':100,'height':30}
    return [dict(group='Colors',id='brand-color',role='textbox',name='Brand color',kind='text',value='#123456',bounds=b),dict(group='Style',id='preset-modern',role='button',name='Modern',kind='choice',value='Modern',bounds=b),dict(group='Typography',id='font-family',role='combobox',name='Font',kind='select',value='Inter',bounds=b)]
class CheckoutThemeProfileTest(unittest.TestCase):
    def test_live_captured_preset_selection_and_readback(self):
        item=dict(group='Presets',id='preset-clay',role='button',name='Clay',kind='choice',value='Clay',bounds={'x':1,'y':2,'width':10,'height':10})
        panel=Panel([item])
        ui._theme_preset(panel,'Clay',write=None)
        ui._theme_preset(panel,'Clay',write=True)
        ui._theme_preset(panel,'Clay',write=False)
        panel.controls['preset-clay'].pressed='false'
        with self.assertRaises(CheckoutRefused): ui._theme_preset(panel,'Clay',write=False)
        with self.assertRaises(CheckoutRefused): ui.validate_checkout_ui({'element_id':'order-form-fixture','expected_name':'Order Form','theme_preset':'Imaginary'})

    def test_apply_and_readback_detects_changed_value(self):
        data=profile(); ui._validate_theme_profile(data); panel=Panel(data)
        ui._theme_profile_controls(panel,data,write=None); ui._theme_profile_controls(panel,data,write=True); ui._theme_profile_controls(panel,data,write=False)
        panel.controls['brand-color'].value='#ffffff'
        with self.assertRaises(CheckoutRefused): ui._theme_profile_controls(panel,data,write=False)
    def test_invalid_capture_refused(self):
        for change in ({'bounds':{'x':0,'y':0,'width':0,'height':1}},{'kind':'choice','role':'button','value':'Different'},{'id':'bad selector]'}):
            data=profile(); data[0].update(change)
            with self.assertRaises(CheckoutRefused): ui._validate_theme_profile(data)
    def test_missing_later_control_blocks_preflight(self):
        data=profile(); panel=Panel(data); panel.controls['font-family'].visible=False
        with self.assertRaises(CheckoutRefused): ui._theme_profile_controls(panel,data,write=None)
        self.assertEqual(panel.controls['brand-color'].value,'old'); self.assertEqual(panel.controls['preset-modern'].pressed,'false')
if __name__ == '__main__': unittest.main()

class TypographyBox:
    def __init__(self): self.value='21'
    def get_by_role(self, *args): return self
    def count(self): return 1
    def is_visible(self): return True
    def wait_for(self, **kwargs): pass
    def get_attribute(self, name): return 'Please Input' if name == 'placeholder' else None
    def input_value(self): return self.value
    def fill(self, value): self.value=value
    def press(self, key): pass
class TypographyRadio:
    def __init__(self, owner, value): self.owner,self.value=owner,value
    def count(self): return 1
    def get_attribute(self, name): return self.value if name=='value' else None
    def is_checked(self): return self.owner.selected==self.value
class TypographyLabel:
    def __init__(self, owner, value): self.owner,self.value=owner,value
    def locator(self, selector): return TypographyRadio(self.owner,self.value)
    def click(self): self.owner.selected=self.value
    def count(self): return 1
    def is_visible(self): return True
class TypographyPanel:
    def __init__(self): self.box=TypographyBox(); self.selected='left'
    def get_by_role(self, *args, **kwargs): return Control({'id':'nav'})
    def get_by_text(self, *args, **kwargs): return Control({'id':'group'})
    def locator(self, selector): return self.box
    def get_by_test_id(self, value): return TypographyLabel(self,value.rsplit('-',1)[-1])
class CapturedTypographyTest(unittest.TestCase):
    def test_typography_apply_and_readback(self):
        panel=TypographyPanel(); wanted={'headline_size_desktop':26,'alignment':'center'}
        ui._theme_typography(panel,wanted,write=None)
        ui._theme_typography(panel,wanted,write=True)
        ui._theme_typography(panel,wanted,write=False)
        self.assertEqual((panel.box.value,panel.selected),('26','center'))
        panel.selected='right'
        with self.assertRaises(CheckoutRefused): ui._theme_typography(panel,wanted,write=False)

class OrderRows:
    def __init__(self,panel): self.panel=panel
    def count(self): return len(self.panel.order)
    def nth(self,i): return OrderRow(self.panel,self.panel.order[i])
class OrderGrip:
    def __init__(self,panel,key): self.panel,self.key=panel,key
    def count(self): return 1
    def get_by_test_id(self, name): return self
    def drag_to(self,target):
        self.panel.order.remove(self.key)
        self.panel.order.insert(self.panel.order.index(target.key),self.key)
class OrderRow:
    def __init__(self,panel,key): self.panel,self.key=panel,key
    def get_attribute(self,name): return 'field-row-'+ui.FIELD_ROW_IDS[self.key]
    def get_by_label(self,*args,**kwargs): return OrderGrip(self.panel,self.key)
class OrderPanel:
    def __init__(self): self.order=list(ui.CONTACT_FIELDS)
    def get_by_role(self,*args,**kwargs): return Control({'id':'nav'})
    def locator(self,selector): return OrderRows(self)
    def get_by_test_id(self,value):
        native=value.replace('field-row-',''); key={v:k for k,v in ui.FIELD_ROW_IDS.items()}[native]
        return OrderRow(self,key)
class CapturedOrderTest(unittest.TestCase):
    def test_order_apply_and_readback(self):
        panel=OrderPanel(); wanted=panel.order.copy(); wanted.insert(1,wanted.pop(4))
        ui._contact_order(panel,wanted,write=None)
        ui._contact_order(panel,wanted,write=True)
        ui._contact_order(panel,wanted,write=False)
        self.assertEqual(panel.order,wanted)
        panel.order.reverse()
        with self.assertRaises(CheckoutRefused): ui._contact_order(panel,wanted,write=False)

class WidthButton:
    def __init__(self): self.state='half'
    def count(self): return 1
    def locator(self, selector): return self
    def get_attribute(self, name):
        return ui.FULL_WIDTH_PATH if self.state=='full' else ui.HALF_WIDTH_PATH_PREFIX+' remainder'
    def click(self): self.state='full' if self.state=='half' else 'half'
class WidthRow:
    def __init__(self,panel): self.panel=panel
    def count(self): return 1
    def wait_for(self,**kwargs): pass
    def locator(self,selector): return WidthLabel()
    def get_by_role(self,role,**kwargs): return self.panel.button
class WidthLabel:
    def count(self): return 1
    def get_attribute(self,name): return 'Phone'
class WidthPanel:
    def __init__(self): self.button=WidthButton()
    def get_by_role(self,*args,**kwargs): return Control({'id':'nav'})
    def get_by_test_id(self,value): return WidthRow(self)
class CapturedWidthTest(unittest.TestCase):
    def test_apply_width_and_detect_failed_readback(self):
        panel=WidthPanel(); requested={'phone':{'width':'full'}}
        ui._contact_fields(panel,requested,write=True)
        self.assertEqual(panel.button.state,'full')
        ui._contact_fields(panel,requested,write=False)
        panel.button.state='half'
        with self.assertRaises(CheckoutRefused): ui._contact_fields(panel,requested,write=False)
    def test_unknown_width_icon_refused(self):
        button=WidthButton(); button.get_attribute=lambda key:'unknown'
        with self.assertRaises(CheckoutRefused): ui._field_width_state(button,'phone')

class ColorTile:
    def __init__(self,panel): self.panel=panel
    def count(self): return 1
    def is_visible(self): return True
    def wait_for(self,**kwargs): pass
    def evaluate(self,script): return self.panel.color
    def click(self): pass
class ColorRow:
    def __init__(self,panel): self.panel=panel
    def filter(self,**kwargs): return self
    def count(self): return 1
    def locator(self,selector): return ColorTile(self.panel)
class ColorEditor:
    def __init__(self,panel,name): self.panel,self.name=panel,name
    def count(self): return 1
    def get_attribute(self,key): return '000000' if self.name=='Enter color value in the selected format' else None
    def fill(self,value): self.panel.values[self.name]=value
    def click(self):
        if self.name=='Save':
            value=self.panel.values['Enter color value in the selected format']
            self.panel.color='rgb('+', '.join(str(int(value[i:i+2],16)) for i in (0,2,4))+')'
class ColorPanel:
    def __init__(self): self.color='rgb(0, 0, 0)';self.values={}
    def get_by_role(self,role,name,exact=True): return ColorEditor(self,name)
    def get_by_text(self,*args,**kwargs): return ColorEditor(self,'label')
    def locator(self,selector): return ColorRow(self)
class CapturedColorTest(unittest.TestCase):
    def test_apply_and_readback(self):
        panel=ColorPanel(); wanted={'accent':'#1234AB'}
        ui._theme_colors(panel,wanted,write=None)
        ui._theme_colors(panel,wanted,write=True)
        ui._theme_colors(panel,wanted,write=False)
        self.assertEqual(panel.values['Enter alpha value from 0 to 100'],'100')
        panel.color='rgb(0, 0, 0)'
        with self.assertRaises(CheckoutRefused): ui._theme_colors(panel,wanted,write=False)
    def test_transparent_swatch_refused(self):
        panel=ColorPanel();panel.color='rgba(1, 2, 3, 0.5)'
        with self.assertRaises(CheckoutRefused): ui._theme_colors(panel,{'accent':'#010203'},write=False)
