"""Rebuild captured paragraph/inline-mark messages through native editor input.

Only unadorned paragraphs and the four captured toolbar marks are accepted.
No HTML is injected into the page; exact native markup must match before Save.
"""
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

if __package__:
    from .skill6_playwright import Stop,click,fill,wait_until
else:
    from skill6_playwright import Stop,click,fill,wait_until

MARKS={'strong':('bold','Bold'),'em':('italic','Italic'),
       'u':('underline','Underline'),'s':('strike','Strikethrough')}


class _Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.roots=[];self.stack=[];self.nodes=0

    def handle_starttag(self,tag,attrs):
        link=tag=='a' and len(attrs)==3 and [key for key,_ in attrs]==['target','rel','href'] and attrs[0][1]=='_blank' and attrs[1][1]=='noopener noreferrer nofollow'
        if link:
            try: url=urlsplit(attrs[2][1]);port=url.port
            except (ValueError,TypeError):raise Stop('Message link URL is malformed') from None
            if url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None or port not in (None,443):
                raise Stop('Message links require credential-free HTTPS URLs')
        if ((attrs and not (tag=='p' and attrs==[('style','')]) and not link) or tag not in {'p','a',*MARKS} or self.nodes>=2000
                or tag=='p' and self.stack
                or tag!='p' and (not self.stack or any(node[0]==tag for node in self.stack))
                or link and any(node[0]!='p' for node in self.stack)
                or tag in MARKS and any(node[0]=='a' for node in self.stack)):
            raise Stop('Message recreation supports captured unstyled paragraphs and inline toolbar marks only')
        node=[tag,[],attrs if link else bool(attrs)];self.nodes+=1
        (self.stack[-1][1] if self.stack else self.roots).append(node)
        self.stack.append(node)

    def handle_endtag(self,tag):
        if not self.stack or self.stack[-1][0]!=tag:
            raise Stop('Message recreation markup is malformed')
        node=self.stack.pop()
        if tag in {*MARKS,'a'} and not node[1]:
            raise Stop('Empty inline message marks cannot be recreated safely')

    def handle_data(self,data):
        if not data:return
        if not self.stack or any(ord(char)<32 for char in data):
            raise Stop('Message recreation requires paragraph boundaries rather than hidden control text')
        self.stack[-1][1].append(data)

    def handle_comment(self,data):
        raise Stop('Message recreation does not retain hidden HTML comments')

    def handle_decl(self,decl):
        raise Stop('Message recreation does not accept HTML declarations')


def _html(node):
    if isinstance(node,str):return escape(node,quote=False)
    attrs=(''.join(' '+key+'="'+escape(value,quote=True)+'"' for key,value in node[2]) if node[0]=='a' else ' style=""' if node[2] else '')
    return '<'+node[0]+attrs+'>'+''.join(_html(child) for child in node[1])+'</'+node[0]+'>'


def parse(markup,*,with_links=False):
    if not isinstance(markup,str) or not markup or len(markup)>200000:
        raise Stop('Message recreation requires the bounded actual native markup')
    parser=_Paragraphs()
    try:parser.feed(markup);parser.close()
    except Stop:raise
    except Exception:raise Stop('Message recreation markup cannot be parsed safely') from None
    if (parser.stack or not 1<=len(parser.roots)<=100
            or any(node[0]!='p' for node in parser.roots)
            or ''.join(_html(node) for node in parser.roots)!=markup):
        raise Stop('Message recreation requires canonical captured paragraph markup')
    paragraphs=[]
    def runs(node,marks,link=None):
        if isinstance(node,str):
            if link is not None and any(ord(char)<32 or ord(char)>126 for char in node):
                raise Stop('Linked message text requires captured single-key characters')
            result=(node,tuple(tag for tag in MARKS if tag in marks))
            return [result+(link,) if with_links else result]
        if node[0]=='a':link=node[2][2][1]
        return [run for child in node[1] for run in runs(child,marks|{node[0]},link)]
    for paragraph in parser.roots:
        values=[run for child in paragraph[1] for run in runs(child,set())]
        if not values or not ''.join(run[0] for run in values):
            raise Stop('Empty message paragraphs need a separate captured native shape')
        paragraphs.append(values)
    return paragraphs


def comparable(markup):
    """Only the captured editor/card empty-style difference is inert."""
    parse(markup)
    return markup.replace('<p style="">','<p>')

def write(modal,control,markup,identity,*,frame=None):
    paragraphs=parse(markup,with_links=True)
    toolbar={}
    for mark,(suffix,label) in MARKS.items():
        node=modal.locator('#richTextEditor #toolbar_button--'+suffix)
        if (node.count()!=1 or not node.is_visible() or not node.is_enabled()
                or node.get_attribute('type')!='button' or node.get_attribute('aria-label')!=label):
            raise Stop('Native conditional message toolbar identity changed: '+label)
        toolbar[mark]=node
    identity();fill(control,'')
    # New outcome editors have the captured unmarked toolbar. Do not infer
    # stored selection marks from empty text or toggle an unknown style away.
    if any((node.get_attribute('class') or '').split()!=['toolbar_button'] for node in toolbar.values()):
        raise Stop('Native new-message toolbar is not in its captured unmarked state')
    active=set()
    def set_marks(wanted):
        for mark in MARKS:
            if (mark in active)!=(mark in wanted):
                identity();click(toolbar[mark])
                if mark in wanted:active.add(mark)
                else:active.remove(mark)
    for index,paragraph in enumerate(paragraphs):
        if index:
            set_marks(set());identity();control.press('Enter')
        for text,marks,link in paragraph:
            set_marks(set(marks));identity();control.press_sequentially(text)
            if link is not None:
                if frame is None:raise Stop('Native link editor requires its exact frame portal')
                for _ in text:control.press('Shift+ArrowLeft')
                button=modal.locator('#richTextEditor').get_by_role('button',name='Add Link',exact=True)
                if button.count()!=1 or not button.is_visible() or not button.is_enabled():
                    raise Stop('Native Add Link toolbar identity changed')
                identity();click(button)
                dialog=modal.get_by_role('dialog')
                if dialog.count()!=1 or not dialog.is_visible():raise Stop('Native Embed Link dialog is unavailable')
                form=dialog.locator('#link-embed_form')
                if form.count()!=1 or not form.is_visible():raise Stop('Native Embed Link form is unavailable')
                href=dialog.locator('#editor_link-embed-href')
                if href.count()!=1 or href.get_attribute('type')!='text':raise Stop('Native link URL input changed')
                identity();fill(href,link)
                if __package__:
                    from .form_conditions import _choose
                else:
                    from form_conditions import _choose
                _choose(frame,'#editor_link-embed-target','New window')
                save=dialog.locator('#editor__link-embed-footer-btn-positive-action')
                if save.count()!=1 or not save.is_visible() or not save.is_enabled():raise Stop('Native link Save changed')
                identity();click(save)
                wait_until(lambda:not dialog.is_visible(),'Native link editor did not close')
                control.press('ArrowRight')
    set_marks(set())
    wait_until(lambda:comparable(control.inner_html())==comparable(markup),
               'Native conditional message markup differs; rule Save not attempted')
