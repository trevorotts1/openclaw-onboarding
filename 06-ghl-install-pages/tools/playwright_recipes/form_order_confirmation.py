"""Payment-owned native form Order Confirmation mode, without charging.

The editor allows this selection even without a payment element. Its canned
preview is never proof of a product binding or successful payment. The caller
must supply a same-form verified checkout contract; the parent runner owns the
writer journal, tenant checks and explicit reconciliation after interruption.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib
import json
import re
from urllib.parse import urlsplit

if __package__:
    from .skill6_playwright import Stop
else:
    from skill6_playwright import Stop


MODES = ('Message', 'Redirect to URL', 'Order Confirmation')
NOTE = 'Order confirmation page will be shown once payment is successful'


def _id(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise Stop('Order Confirmation requires an exact native ' + label)
    return value


def validate(step):
    if (not isinstance(step, dict)
            or set(step) - {'id', 'action', 'payload'}
            or step.get('action', 'native_order_confirmation') != 'native_order_confirmation'):
        raise Stop('Unsupported native Order Confirmation action')
    data = step.get('payload')
    if (not isinstance(data, dict)
            or set(data) != {'location_id','location_name','start_url','form_id','expected_form_name',
                             'expected_mode','checkout_contract','ack_conditional_precedence'}):
        raise Stop('Order Confirmation requires an explicit same-form payment configuration')
    _id(data['location_id'], 'location_id'); _id(data['form_id'], 'form_id')
    if (not isinstance(data['location_name'], str) or not data['location_name'].strip()
            or not isinstance(data['expected_form_name'], str) or not data['expected_form_name'].strip()
            or data['expected_mode'] not in MODES
            or type(data['ack_conditional_precedence']) is not bool):
        raise Stop('Order Confirmation requires inventoried form identity, previous mode and real acknowledgment boolean')
    url = urlsplit(data['start_url']) if isinstance(data['start_url'], str) else None
    if (url is None or url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment
            or url.path.rstrip('/') != '/v2/location/' + data['location_id'] + '/form-builder-v2/' + data['form_id']):
        raise Stop('Order Confirmation editor URL must identify its exact location and form')
    contract = data['checkout_contract']
    required = {'status','source','location_id','form_id','product_id','product_name','product_type',
                'price_id','price_name','price','display_amount','expected_selected','observed_at'}
    if (not isinstance(contract, dict) or set(contract) != required
            or contract['status'] != 'PASS'
            or not isinstance(contract['source'], str) or not contract['source'].strip()
            or contract['location_id'] != data['location_id'] or contract['form_id'] != data['form_id']):
        raise Stop('Order Confirmation requires its complete same-form checkout inventory')
    for key in ('product_id','price_id'):
        _id(contract[key], key)
    for key in ('product_name','product_type','price_name','display_amount'):
        if (not isinstance(contract[key],str) or not contract[key].strip()
                or any(ord(c)<32 for c in contract[key])):
            raise Stop('Checkout inventory requires exact catalog/display text: ' + key)
    if contract['product_type'] not in ('DIGITAL','PHYSICAL','SERVICE','PHYSICAL/DIGITAL'):
        raise Stop('Checkout product type is unsupported')
    if type(contract['expected_selected']) is not bool:
        raise Stop('Checkout checkbox state must be explicitly inventoried, not selected by this operation')
    from playwright_recipes.pages_checkout import native
    try:
        price = native.validate_price_ref(contract['price'])
    except native.OrderComponentError:
        raise Stop('Checkout terms are malformed') from None
    if (price.native_product_id != contract['product_id'] or price.native_price_id != contract['price_id']
            or price.amount_minor <= 0 or price.currency != 'USD' or price.billing_type != 'recurring'
            or price.recurring_interval != 'month' or price.trial_days is not None):
        raise Stop('Captured form-payment display supports exact USD monthly recurring terms without trial only')
    amount = re.fullmatch(r'\$([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)/month',contract['display_amount'])
    if not amount or Decimal(amount.group(1).replace(',','')) * 100 != price.amount_minor:
        raise Stop('Native displayed monthly amount differs from approved exact minor-unit terms')
    if not isinstance(contract['observed_at'], str):
        raise Stop('Payment-binding observation time must be an explicit aware ISO timestamp')
    try:
        timestamp = datetime.fromisoformat(contract['observed_at'].replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            raise ValueError('naive')
    except ValueError:
        raise Stop('Payment-binding observation time must be an explicit aware ISO timestamp') from None
    return deepcopy(step)


def configuration_hash(step):
    return hashlib.sha256(json.dumps(validate(step)['payload'], sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _fresh(contract):
    observed = datetime.fromisoformat(contract['observed_at'].replace('Z', '+00:00'))
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    if not 0 <= age <= 3600:
        raise Stop('Payment-binding inventory is stale; refresh the same-form checkout contract before writing')


def _one(node, reason):
    try:
        node.wait_for(state='visible', timeout=45000)
    except Exception:
        raise Stop(reason) from None
    if node.count() != 1 or not node.is_visible():
        raise Stop(reason)
    return node


def _mode(frame):
    selected = _one(frame.locator('#submit .n-base-selection-input'),
                    'Native On Submit selector identity changed')
    label = _one(selected.locator('.n-base-selection-input__content'),
                 'Native On Submit selected label changed').inner_text().strip()
    if label not in MODES or selected.get_attribute('title') != label:
        raise Stop('Native On Submit mode is unavailable or inconsistent')
    return selected, label


def _confirmation(frame):
    _one(frame.get_by_text(NOTE, exact=True), 'Native successful-payment confirmation notice changed')
    _one(frame.locator('.preview-container.preview-container--order'),
         'Native Order Confirmation preview shape changed')


def _settings(frame):
    """Protect the captured scheduler/ordinary switches through the mode save."""
    from playwright_recipes.skill6_playwright import FORM_SETTINGS
    switches = frame.get_by_role('switch')
    if switches.count() not in (8, 9):
        raise Stop('Native form Settings switch inventory changed')
    def row_text(control):
        return control.evaluate('''el => {
            for (const row of [el.parentElement, el.parentElement?.parentElement]) {
                if (row && row.querySelectorAll('[role="switch"]').length === 1
                        && row.textContent.trim()) return row.textContent;
            }
            return '';
        }''')
    def read(control, label):
        if label not in row_text(control) or control.get_attribute('aria-checked') not in ('true', 'false'):
            raise Stop('Native form Settings switch identity/state changed: ' + label)
        return control.get_attribute('aria-checked') == 'true'
    scheduled = read(switches.nth(0), 'Schedule form visibility')
    offset = int(scheduled)
    if switches.count() != 8 + offset:
        raise Stop('Native form Settings switch count differs from scheduler state')
    values = {'schedule_visibility':scheduled}
    if scheduled:
        values['agency_branding'] = read(switches.nth(1), 'Agency branding')
    for key,(index,label) in FORM_SETTINGS.items():
        values[key] = read(switches.nth(index+offset), label)
    return values


class ReadOnlyCatalog:
    """Reuse the canonical products/prices adapter and existing PIT resolver."""
    def __init__(self):
        from playwright_recipes.delivery import Skill44Transport
        self.client = Skill44Transport().client
        cli = importlib.import_module('cli_anything.gohighlevel.gohighlevel_cli')
        self.pp = cli._products_prices()
        pp, client = self.pp, self.client
        class Transport:
            def request(self, method, path, body=None):
                if method != 'GET' or body is not None:
                    raise Stop('Order Confirmation catalog guard never writes products or prices')
                try:
                    result = client.get(path, version=pp.API_VERSION)
                except Exception as error:
                    status = getattr(getattr(error, 'response', None), 'status_code', None)
                    if status in (401, 403):
                        from ghl_auth import AuthBridgeError
                        raise AuthBridgeError('Canonical payment catalog authorization denied; no alternate lane') from None
                    raise
                if not isinstance(result, dict):
                    raise Stop('Native catalog read returned no authoritative object')
                return pp.Response(200, result)
        self.adapter = pp.ProductsPricesAdapter(Transport(), pp.InMemoryStore())

    def verify(self, contract):
        pp, adapter = self.pp, self.adapter
        product_spec = pp.ProductSpec(contract['product_name'], contract['location_id'], contract['product_type'])
        product = adapter._read_product(contract['product_id'], product_spec)
        terms = contract['price']
        spec = pp.PriceSpec(name=contract['price_name'], location_id=contract['location_id'],
            billing_type=terms['billing_type'], currency=terms['currency'], amount_minor=terms['amount_minor'],
            recurring_interval=terms['recurring_interval'], trial_days=terms['trial_days'])
        price = adapter._read_price(product, contract['price_id'], spec)
        # The native form does not expose a price ID. Only a complete one-price
        # catalog makes its displayed product/terms unambiguous; never pick the
        # first of multiple monthly/annual prices or bless a truncated list.
        from urllib.parse import quote
        listed = adapter._call('list_prices', {'productId':contract['product_id'],
                                              'locationId':quote(contract['location_id'],safe='')})
        rows = listed.get('prices') if isinstance(listed,dict) else None
        if (not isinstance(rows,list) or type(listed.get('total')) is not int
                or listed['total'] != 1 or len(rows) != 1
                or not isinstance(rows[0],dict) or rows[0].get('_id') != contract['price_id']):
            raise Stop('Native form price identity is unavailable unless the complete product catalog has exactly one price')
        verified = price.as_price_ref_fields()
        if verified != contract['price']:
            raise Stop('Canonical price readback differs from the complete approved payment terms')
        return {'product_id':product.native_product_id, 'price':verified, 'price_identity':'UNIQUE_CATALOG_PRICE'}


def _payment(frame, contract):
    """Bind the one captured payment canvas row without inventing an element ID."""
    labels = frame.locator('label[data-field-type="payment"]')
    if labels.count() != 1:
        raise Stop('Order Confirmation requires exactly one inventoried native payment element')
    item = _one(frame.locator('.form-builder--item').filter(has=labels),
                'Native payment element owner is missing or ambiguous')
    rows = item.locator('section.product-layout > .product-container')
    if rows.count() != 1:
        raise Stop('Captured Order Confirmation supports exactly one configured native product row')
    row = rows.nth(0)
    checkbox = row.locator('input[type="checkbox"]')
    if checkbox.count() != 1 or any(checkbox.get_attribute(key) != contract['product_id']
                                    for key in ('id','name','value')):
        raise Stop('Native payment checkbox does not identify the exact inventoried product')
    name = _one(row.locator('.product-label'),'Native payment product label changed').inner_text().strip()
    amount = _one(row.locator('.product-amount'),'Native payment price display changed').inner_text().strip()
    selected = checkbox.is_checked()
    if (name != contract['product_name'] or amount != contract['display_amount']
            or selected is not contract['expected_selected']):
        raise Stop('Native payment product, displayed amount or checkbox state differs from its inventory')
    return {'product_id':contract['product_id'], 'name':name, 'amount':amount, 'selected':selected}


def configure(page, step, *, catalog=None):
    """Set only the native outcome, save once, independently reopen and inspect.

    Canonical catalog GETs are read-only and never create a product/price. The
    native product checkbox is inventoried and preserved, never clicked. The
    canned order preview proves only that the editor selected the outcome.
    """
    from playwright_recipes.skill6_playwright import assert_tenant, click, form_builder, wait_until
    from playwright_recipes.field_placement import _close_initial
    from playwright_recipes.assessments import reopen_editor
    plan = validate(step); data = plan['payload']; contract = data['checkout_contract']
    _fresh(contract)
    if page.url != data['start_url']:
        raise Stop('Open the exact inventoried form editor before its payment-owned outcome')
    assert_tenant(page,data)
    frame = form_builder(page)
    title = _one(frame.get_by_role('textbox',name='Form Name',exact=True),
                 'Native payment form title changed')
    if title.input_value() != data['expected_form_name']:
        raise Stop('Native payment form name differs from its inventoried identity')
    def identity():
        if page.url != data['start_url'] or title.count()!=1 or title.input_value()!=data['expected_form_name']:
            raise Stop('Native payment form identity changed during outcome configuration')
        assert_tenant(page,data)
    def payment():
        identity(); _close_initial(frame)
        click(_one(frame.get_by_role('tab',name='Edit',exact=True),'Native form Edit tab changed'))
        return _payment(frame,contract)
    def settings():
        identity(); _close_initial(frame)
        click(_one(frame.get_by_role('tab',name='Settings',exact=True),'Native form Settings tab changed'))
        return _mode(frame)
    before_payment = payment()
    reader = catalog or ReadOnlyCatalog()
    before_catalog = reader.verify(contract)
    selector, before_mode = settings()
    if before_mode != data['expected_mode']:
        raise Stop('Native On Submit mode differs from the expected previous value')
    before_settings = _settings(frame)
    warning = frame.get_by_text(re.compile('Conditional logic will take precedence',re.I))
    precedence = any(warning.nth(index).is_visible() for index in range(warning.count()))
    if precedence and data['ack_conditional_precedence'] is not True:
        raise Stop('Existing conditional logic overrides the payment outcome; explicit acknowledgment is required')
    changed = before_mode != 'Order Confirmation'
    if changed:
        identity(); click(selector)
        option = frame.locator('.n-base-select-option').get_by_text('Order Confirmation',exact=True)
        click(_one(option,'Native Order Confirmation choice changed'))
        wait_until(lambda:_mode(frame)[1]=='Order Confirmation','Native payment outcome did not change')
    _confirmation(frame)
    if _settings(frame) != before_settings or payment()!=before_payment or reader.verify(contract)!=before_catalog:
        raise Stop('Payment outcome pre-save inspection lost a protected setting, product or catalog binding')
    if settings()[1]!='Order Confirmation':
        raise Stop('Native payment outcome changed while preflighting its preserved product')
    _confirmation(frame)
    if changed:
        identity()
        save = _one(frame.get_by_role('button',name='Save',exact=True),'Native form Save changed')
        if not save.is_enabled():
            raise Stop('Native form cannot save the requested payment outcome')
        click(save)
        wait_until(lambda:save.is_enabled(),'Native payment outcome Save did not settle')
    reopen_editor(page,'form',data['expected_form_name'],data['start_url'])
    frame = form_builder(page)
    title = _one(frame.get_by_role('textbox',name='Form Name',exact=True),'Reopened payment form title changed')
    if settings()[1]!='Order Confirmation' or _settings(frame)!=before_settings:
        raise Stop('Native Order Confirmation or protected Settings did not persist after independent reopen')
    _confirmation(frame)
    if payment()!=before_payment or reader.verify(contract)!=before_catalog:
        raise Stop('Persisted payment outcome lost its exact native product/catalog binding')
    if settings()[1]!='Order Confirmation':
        raise Stop('Reopened payment form outcome changed after independent product readback')
    _confirmation(frame)
    return {'status':'ORDER_CONFIRMATION_SAVED_AND_REOPENED' if changed else 'ORDER_CONFIRMATION_REUSED_AND_REOPENED',
        'editor_url':page.url,'form_id':data['form_id'],'product_id':contract['product_id'],
        'price_id':contract['price_id'],'price_identity':'UNIQUE_CATALOG_PRICE',
        'configuration_sha256':configuration_hash(plan),'independent_readback':'VERIFIED',
        'conditional_precedence_present':precedence,
        'conditional_precedence_acknowledged':data['ack_conditional_precedence'],
        'payment_verified':False,'submission_verified':False,'behavior_verified':False}


def validate_receipt(result, step):
    """Validate saved outcome identity and pending proof without aging replay."""
    data = validate(step)['payload']; contract = data['checkout_contract']
    expected_status = ('ORDER_CONFIRMATION_REUSED_AND_REOPENED' if data['expected_mode']=='Order Confirmation'
                       else 'ORDER_CONFIRMATION_SAVED_AND_REOPENED')
    if (not isinstance(result,dict) or result.get('status')!=expected_status
            or result.get('editor_url')!=data['start_url']
            or result.get('form_id')!=data['form_id']
            or result.get('product_id')!=contract['product_id'] or result.get('price_id')!=contract['price_id']
            or result.get('price_identity')!='UNIQUE_CATALOG_PRICE'
            or result.get('configuration_sha256')!=configuration_hash(step)
            or result.get('independent_readback')!='VERIFIED'
            or result.get('conditional_precedence_acknowledged') is not data['ack_conditional_precedence']
            or type(result.get('conditional_precedence_present')) is not bool
            or result['conditional_precedence_present'] and not data['ack_conditional_precedence']
            or any(result.get(key) is not False for key in (
                'payment_verified','submission_verified','behavior_verified'))):
        raise Stop('Native payment outcome receipt is unbound or overclaims payment behavior')
    return True
