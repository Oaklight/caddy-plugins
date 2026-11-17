import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = "https://hub.docker.com/v2"
USER = os.environ["DOCKERHUB_USERNAME"]
TOKEN = os.environ["DOCKERHUB_TOKEN"]
REPOS = [r for r in re.split(r"[,\s]+", os.environ.get("DOCKERHUB_REPOSITORIES", "")) if r]
README = os.environ.get("README_FILE", "README_en.md")
SHORT = (os.environ.get("SHORT_DESCRIPTION") or "").strip()[:100]
SHORT_MAP = json.loads(os.environ.get("SHORT_MAP") or "{}")
README_MAP = json.loads(os.environ.get("README_MAP") or "{}")
DRY = os.environ.get("DRY_RUN") == "1"
SLUG = os.environ["GITHUB_REPOSITORY"]
REF = os.environ.get("GITHUB_REF_NAME") or "main"
LIMIT = 24000

ABS = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|#|//|/)")


def for_dockerhub(md):
    """Adapt a GitHub README for the Docker Hub renderer.

    Docker Hub forces every image to display:block and strips style
    attributes, so centered logo and badge rows collapse into a left-aligned
    stack. Keep one logo (the light-background variant), drop the badge rows,
    and leave the prose alone.
    """
    logo = []

    def take_picture(m):
        block = m.group(0)
        img = re.search(r"<img\b[^>]*>", block, re.I)
        chosen = None
        for sm in re.finditer(r"<source\b[^>]*>", block, re.I):
            tag = sm.group(0)
            media = re.search(r'media="([^"]*)"', tag, re.I)
            srcset = re.search(r'srcset="([^"]*)"', tag, re.I)
            if not srcset:
                continue
            candidate = srcset.group(1).split()[0]
            if chosen is None:
                chosen = candidate
            if media and "light" in media.group(1).lower():
                chosen = candidate
                break
        if not img and not chosen:
            return ""
        if img:
            tag = img.group(0)
            if chosen:
                tag = re.sub(r'\bsrc="[^"]*"', 'src="%s"' % chosen, tag, count=1, flags=re.I)
        else:
            tag = '<img src="%s" alt="">' % chosen
        tag = re.sub(r'\bwidth="[^"]*"', 'width="96"', tag, flags=re.I)
        if not re.search(r"\bwidth=", tag, re.I):
            tag = (tag[:-2] + ' width="96">') if tag.rstrip().endswith("/>") else (tag[:-1] + ' width="96">')
        logo.append(tag)
        return "@@LOGO@@"

    md = re.sub(r"<picture\b[^>]*>.*?</picture>", take_picture, md, flags=re.S | re.I)

    def image_only_para(m):
        text = re.sub(r"<[^>]+>", "", m.group(1))
        return "" if not text.strip() else m.group(0)

    md = re.sub(r"<p\b[^>]*>(.*?)</p>", image_only_para, md, flags=re.S | re.I)

    kept = []
    for line in md.split("\n"):
        stripped = line.strip()
        if stripped and re.fullmatch(r"(?:\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)[\s,]*)+", stripped):
            continue
        kept.append(line)
    md = "\n".join(kept)

    md = re.sub(r"<h1\b[^>]*>(.*?)</h1>",
                lambda m: "# " + re.sub(r"<[^>]+>", "", m.group(1)).strip(),
                md, flags=re.S | re.I)

    if logo:
        md = md.replace("@@LOGO@@", logo[0], 1)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def absolutize(md, slug, ref):
    """Point relative links at GitHub so Docker Hub can render them."""
    raw = "https://raw.githubusercontent.com/%s/%s/" % (slug, ref)
    blob = "https://github.com/%s/blob/%s/" % (slug, ref)

    def one(url, image):
        if not url or ABS.match(url):
            return url
        url = url[2:] if url.startswith("./") else url
        return (raw if image else blob) + url

    def srcset(value):
        out = []
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            bits = item.split(None, 1)
            bits[0] = one(bits[0], True)
            out.append(" ".join(bits))
        return ", ".join(out)

    md = re.sub(r"(!\[[^\]]*\]\()([^)\s]+)", lambda m: m.group(1) + one(m.group(2), True), md)
    md = re.sub(r"(?<!!)(\[[^\]]*\]\()([^)\s]+)", lambda m: m.group(1) + one(m.group(2), False), md)

    def attr(m):
        name, value = m.group(1), m.group(3)
        low = name.lower()
        fixed = srcset(value) if low == "srcset" else one(value, low == "src")
        return "%s=%s%s%s" % (name, m.group(2), fixed, m.group(4))

    md = re.sub(r"""\b(src|srcset|href)\s*(=)\s*(["'])([^"']*)\3""",
                lambda m: m.group(1) + "=" + m.group(3) + (
                    srcset(m.group(4)) if m.group(1).lower() == "srcset"
                    else one(m.group(4), m.group(1).lower() == "src")
                ) + m.group(3), md)
    return md


def http(method, url, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "JWT " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


if not USER or not TOKEN:
    print("::warning::DOCKERHUB_USERNAME and DOCKERHUB_TOKEN are not set; description sync skipped")
    sys.exit(0)

status, out = http("POST", BASE + "/users/login/", {"username": USER, "password": TOKEN})
if status != 200 or "token" not in out:
    sys.exit("::error::Docker Hub login failed (%s): %s" % (status, str(out)[:300]))
jwt = out["token"]

def payload(readme):
    if not os.path.exists(readme):
        return None
    with open(readme, encoding="utf-8") as fh:
        md = fh.read()
    md = absolutize(for_dockerhub(md), SLUG, REF).strip()
    if len(md) > LIMIT:
        print("::warning::%s is %d chars, truncated to %d" % (readme, len(md), LIMIT))
        md = md[:LIMIT].rsplit("\n", 1)[0] + "\n\n<!-- Truncated. Read the full README on GitHub. -->\n"
    return md

failed = False
for repo in REPOS:
    readme = README_MAP.get(repo, README)
    md = payload(readme)
    if md is None:
        print("::error::%s not found for %s" % (readme, repo))
        failed = True
        continue
    status, cur = http("GET", "%s/repositories/%s/" % (BASE, repo))
    if status == 404:
        print("::warning::%s does not exist on Docker Hub yet, skipped" % repo)
        continue
    if status != 200:
        print("::error::GET %s failed (%s)" % (repo, status))
        failed = True
        continue

    want = {"full_description": md}
    short = SHORT_MAP.get(repo, SHORT)
    if short:
        want["description"] = short[:100]
    changed = [k for k, v in want.items() if (cur.get(k) or "").strip() != v.strip()]
    if not changed:
        print("%s: already up to date" % repo)
        continue

    print("%s: %s (%d -> %d chars)" % (
        repo, "would update " + ", ".join(changed) if DRY else "updating " + ", ".join(changed),
        len((cur.get("full_description") or "").strip()), len(md)))
    if DRY:
        continue

    status, out = http("PATCH", "%s/repositories/%s/" % (BASE, repo), want, jwt)
    if status in (200, 201):
        print("%s: updated" % repo)
    else:
        print("::error::PATCH %s failed (%s): %s" % (repo, status, str(out)[:300]))
        failed = True

sys.exit(1 if failed else 0)
