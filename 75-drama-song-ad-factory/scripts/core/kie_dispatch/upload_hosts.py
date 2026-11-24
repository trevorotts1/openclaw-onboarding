"""kie_dispatch.upload_hosts: the ONE place a KIE host is named (F-QM-7).

The F14 static check (`qc-no-direct-kie.sh`, no-direct-kie) fails any KIE host
string literal in a non-test file outside ``kie_dispatch/``. The dispatcher's
own static check (`test_kie_dispatch.py`, "no private KIE client") fails the
words ``urllib`` / ``http.client`` / ``socket`` inside ``kie_dispatch.py``
itself. Both are satisfied by keeping the host list and the URL splitter here:
every other module imports from this one, and ``kie_dispatch.py`` carries
neither a host literal nor a parser import.
"""
from urllib.parse import urlsplit


#: kie.ai is KIE's registered domain; kieai.redpandaai.co is the host Skill 74
#: actually posts an upload to. A link on either is the only kind a paid job may
#: fetch (plan F-QM-7).
KIE_UPLOAD_HOSTS = ("kie.ai", "kieai.redpandaai.co")


def host_of(url):
    """The lower-case host of a URL, or "" when it cannot be parsed."""
    try:
        return (urlsplit(url or "").hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def is_kie_upload(url):
    """True only for a link on KIE's own upload service (F-QM-7)."""
    host = host_of(url)
    return bool(host) and any(
        host == h or host.endswith("." + h) for h in KIE_UPLOAD_HOSTS)
