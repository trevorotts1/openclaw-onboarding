"""Property test: whole-token placeholder matching never rejects a realistic key.

20,000 random keys per provider family (seeded, no network, synthetic only) must give
0 placeholder-word rejections (is_placeholder). The separate, pre-existing 3.0
bits/char entropy floor is counted and reported, not a placeholder match. The placeholder list
must still reject every placeholder value. Run: python3 tests/unit/test_placeholder_property.py
"""
import os, random, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared-utils"))
import secret_helper as s

N = 20000
AN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
B64 = AN + "_-"
HEX = "0123456789abcdef"
r = random.Random(20261006)
def g(alpha, n): return "".join(r.choice(alpha) for _ in range(n))

FAMILIES = {
    "OPENAI_API_KEY":     lambda: "sk-proj-" + g(B64, r.randint(48, 160)),
    "ANTHROPIC_API_KEY":  lambda: "sk-ant-api03-" + g(B64, r.randint(90, 108)),
    "GEMINI_API_KEY":     lambda: "AIza" + g(B64, 35),
    "GOOGLE_API_KEY":     lambda: "AIza" + g(B64, 35),
    "OPENROUTER_API_KEY": lambda: "sk-or-v1-" + g(HEX, 64),
    "GITHUB_TOKEN":       lambda: "ghp_" + g(AN, 36),
    "BRAVE_API_KEY":      lambda: "BSA" + g(AN[:52], 1) + g(B64, r.randint(24, 40)),
    "TAVILY_API_KEY":     lambda: "tvly-" + g(B64, r.randint(24, 40)),
    "DEEPSEEK_API_KEY":   lambda: "sk-" + g(HEX, 32),
    "OLLAMA_API_KEY":     lambda: g(AN, r.randint(32, 64)),
    "KIE_API_KEY":        lambda: g(HEX, 32),
    "KIE_API_KEY ":       lambda: g(AN, 32),
    "TELEGRAM_BOT_TOKEN": lambda: g("0123456789", 10) + ":" + g(B64, 35),
    "SUPABASE_SERVICE_ROLE_KEY": lambda: "eyJ" + g(B64, 30) + "." + g(B64, 60) + "." + g(B64, 43),
    "GOHIGHLEVEL_API_KEY": lambda: "pit-" + g(B64, 36),
    "GOHIGHLEVEL_LOCATION_ID": lambda: g(AN, 20),
    "ELEVENLABS_API_KEY": lambda: "sk_" + g(B64, 48),
    "CONTEXT7_API_KEY":   lambda: "ctx7sk-" + g(B64, 36),
}
bad = 0
floor = 0
for fam, mk in FAMILIES.items():
    keys = [mk() for _ in range(N)]
    ph = [k for k in keys if s.is_placeholder(k)]  # rejected as a placeholder word/template
    ef = [k for k in keys if not s.is_placeholder(k) and not s.looks_like_real_key(k, fam.strip())]
    print("%-26s %d keys, %d placeholder rejections, %d entropy-floor" % (fam.strip(), N, len(ph), len(ef)))
    bad += len(ph)
    floor += len(ef)

PLACEHOLDERS = ["YOUR_CLIENT_KIE_API_KEY_HERE", "your-demo-key-abcdef", "demo_key_abcdef123", "KEY_HERE_ABCDEF123",
                "sk-example1234567890", "xxxxxxxxxxxxxxxx", "<TODO_fill_this_in>", "paste_real_token_now",
                "AKIAIOSFODNN7EXAMPLE", "your_key_here_please", "CHANGE_ME_LATER_ok", "none_yet_abcdef"]
miss = [p for p in PLACEHOLDERS if s.looks_like_real_key(p, None)]
# whole-token: a word inside a random run is NOT a placeholder
inside = [s.looks_like_real_key("Qx7" + w + "Lm9Zk2Pq8Rt4Vb6Nc3Hd5", "KIE_API_KEY") for w in ("demo", "todo", "sample", "tbd", "here", "missing", "unset")]
assert bad == 0, "placeholder false rejections: %d" % bad
assert not miss, "placeholders accepted: %r" % miss
assert all(inside), "word inside an alphanumeric run was rejected"
print("placeholder property test: PASS (0 placeholder false rejections; %d keys under the pre-existing 3.0 entropy floor; %d placeholders rejected)" % (floor, len(PLACEHOLDERS)))
