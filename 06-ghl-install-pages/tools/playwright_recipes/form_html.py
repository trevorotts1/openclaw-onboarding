"""Captured existing custom HTML widgets with native CodeMirror input.

Source is read from numbered rendered CodeMirror lines; no hidden framework data
or editor instance is used. Refuse virtualized source before any mutation.
"""
from playwright_recipes.skill6_playwright import Stop, click, wait_until


def validate_html(value):
    if not isinstance(value,str) or len(value)>20000 or any(ord(c)<32 and c!='\n' for c in value):
        raise Stop('Captured custom HTML requires explicit source up to 20000 characters with LF line breaks')
    return value


def _one(node,message):
    if node.count()!=1 or not node.is_visible():raise Stop(message)
    return node


def _open(frame):
    click(_one(frame.locator('#editHtml'),'Custom HTML Edit control changed'))
    modal=frame.get_by_role('dialog')
    modal.wait_for(state='visible',timeout=45000)
    _one(modal,'Custom HTML editor is ambiguous')
    if _one(modal.locator('.title'),'Custom HTML editor title changed').inner_text().strip()!='CUSTOM JAVASCRIPT / HTML':
        raise Stop('Custom HTML modal title changed')
    _one(modal.locator('.CodeMirror'),'Custom HTML CodeMirror editor changed')
    return modal


def _source(modal):
    box=_one(modal.locator('.CodeMirror'),'Custom HTML CodeMirror editor changed')
    editor=modal.locator('.CodeMirror textarea')
    if editor.count()!=1:raise Stop('Custom HTML native editing textarea changed')

    def rendered():
        rows=modal.locator('.CodeMirror-code > div')
        if not rows.count():raise Stop('Custom HTML rendered source is empty')
        result=[]
        for index in range(rows.count()):
            row=rows.nth(index)
            number=row.locator('.CodeMirror-linenumber')
            line=row.locator('pre.CodeMirror-line')
            if number.count()!=1 or line.count()!=1 or number.inner_text().strip()!=str(index+1):
                raise Stop('Custom HTML rendered line numbers are incomplete or virtualized')
            source=line.inner_text()
            if source=='\u200b' and line.locator('span[cm-text=""]').count()==1:source=''
            result.append(source)
        return result

    # Compare both ends of the editor: a virtualized viewport replaces rendered
    # rows when the caret moves, making the source unsafe to read or replace.
    click(box)
    editor.press('ControlOrMeta+Home')
    first=rendered()
    editor.press('ControlOrMeta+End')
    last=rendered()
    if first!=last:raise Stop('Custom HTML rendered source is virtualized')
    return validate_html('\n'.join(first))


def read_html(frame):
    modal=_open(frame);source=_source(modal)
    click(_one(modal.locator('#modal-footer-btn-negative-action'),'Custom HTML Cancel Keep changed'))
    modal.wait_for(state='hidden',timeout=45000)
    return source


def write_html(frame,before,desired):
    validate_html(desired)
    modal=_open(frame)
    if _source(modal)!=before:raise Stop('Custom HTML source changed after preflight')
    if desired==before:
        click(_one(modal.locator('#modal-footer-btn-negative-action'),'Custom HTML Cancel Keep changed'))
    else:
        click(_one(modal.locator('.CodeMirror'),'Custom HTML CodeMirror editor changed'))
        editor=modal.locator('.CodeMirror textarea')
        if editor.count()!=1:raise Stop('Custom HTML native editing textarea changed')
        editor.press('ControlOrMeta+A')
        if desired:
            editor.press_sequentially(desired)
        else:
            editor.press('Backspace')
        # CodeMirror binds Tab to indentation. Blur through the captured modal
        # heading so the authored source remains byte-for-byte unchanged.
        click(_one(modal.locator('.title'),'Custom HTML blur heading changed'))
        wait_until(lambda:_source(modal)==desired,'Custom HTML source input did not settle')
        click(_one(modal.locator('#modal-footer-btn-positive-action'),'Custom HTML Yes Save changed'))
    modal.wait_for(state='hidden',timeout=45000)


def confirm_save_warning(frame):
    """Confirm only the captured HTML warning after the outer form Save."""
    dialogs=frame.locator('.n-card.n-modal.hl-modal[role="dialog"]:visible')
    if not dialogs.count():return
    dialog=_one(dialogs,'Native form Save dialog is ambiguous')
    title=_one(dialog.locator('.title'),'Native form Save warning title changed')
    description=_one(dialog.locator('.description'),'Native form Save warning text changed')
    expected=('Third-party scripts inside the HTML block can provide powerful functionality, but they also bring risks '
              'to privacy, security, performance and page behavior. Therefore, we recommend that you to review the '
              'contents of this script before saving it to the form.')
    if title.inner_text().strip()!='Alert!' or description.inner_text().strip()!=expected:
        raise Stop('Unrecognized native form Save dialog')
    proceed=_one(dialog.get_by_role('button',name='Proceed',exact=True),'Native HTML warning Proceed changed')
    click(proceed)
    dialog.wait_for(state='hidden',timeout=45000)
