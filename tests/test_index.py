"""เทสต์หน้าเว็บ index.html (ระบบรับสมัครสมาชิกแบบ iframe และปุ่มลอยไประบบรวมเครื่องมือ)

    python3 -m unittest discover -s tests -v
"""

import os
import re
import unicodedata
import unittest
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_URL = "https://envburiramclub.github.io/claude-code/"
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SOURCE_EXTENSIONS = (".html", ".css", ".js", ".py", ".md", ".svg", ".json", ".yml", ".yaml", ".txt")


class _Tags(HTMLParser):
    """เก็บทุกแท็กพร้อม attribute และแท็กแม่ (ใช้ตรวจว่าปุ่มเป็นลูกของ <body> โดยตรง)"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs), self.stack[-1] if self.stack else None))
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, dict(attrs), self.stack[-1] if self.stack else None))

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack.pop() != tag:
                pass


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


def css_rule(css, selector):
    """คืนเนื้อในวงเล็บ { } ของ selector แรกที่ตรงตัว"""
    match = re.search(r"(?:^|[}\s])" + re.escape(selector) + r"\s*\{([^{}]*)\}", css)
    return match.group(1) if match else None


class IndexPageTest(unittest.TestCase):
    def setUp(self):
        self.html = read("index.html")
        parser = _Tags()
        parser.feed(self.html)
        parser.close()
        self.tags = parser.tags
        self.css = re.search(r"<style>(.*?)</style>", self.html, re.S).group(1)
        self.script = re.search(r"<script>(.*?)</script>", self.html, re.S).group(1)

    def fab(self):
        found = [(attrs, parent) for tag, attrs, parent in self.tags
                 if tag == "a" and "tools-fab" in (attrs.get("class") or "").split()]
        self.assertEqual(len(found), 1, "ต้องมีปุ่มลอยรวมเครื่องมือหนึ่งปุ่ม")
        return found[0]

    def test_tools_button_links_to_claude_code(self):
        attrs, _ = self.fab()
        self.assertEqual(attrs.get("href"), TOOLS_URL)
        self.assertEqual(attrs.get("id"), "tools-fab")
        self.assertIn("รวมเครื่องมือ", attrs.get("aria-label") or "", "ปุ่มไอคอนต้องมีชื่อให้โปรแกรมอ่านหน้าจอ")

    def test_tools_button_does_not_leak_referrer_or_opener(self):
        # URL หน้านี้อาจมีพารามิเตอร์ของสมาชิก ห้ามส่งไปกับลิงก์ และแท็บใหม่ต้องไม่ได้ window.opener
        attrs, _ = self.fab()
        self.assertEqual(attrs.get("target"), "_blank")
        rel = (attrs.get("rel") or "").split()
        self.assertIn("noopener", rel)
        self.assertIn("noreferrer", rel)

    def test_every_new_tab_link_has_noopener(self):
        for tag, attrs, _ in self.tags:
            if tag == "a" and attrs.get("target") == "_blank":
                with self.subTest(href=attrs.get("href")):
                    self.assertIn("noopener", (attrs.get("rel") or "").split())
                    self.assertTrue((attrs.get("href") or "").startswith("https://"))

    def test_tools_button_is_direct_child_of_body(self):
        # สคริปต์ใช้ body.insertBefore(frame, ปุ่ม) ถ้าปุ่มไม่ใช่ลูกของ body จะ error และไม่แสดงระบบสมาชิก
        _, parent = self.fab()
        self.assertEqual(parent, "body")
        self.assertIn('document.body.insertBefore(frame, document.getElementById("tools-fab"))', self.script)
        self.assertNotIn("appendChild(frame)", self.script)

    def test_icon_is_decorative(self):
        icons = [(attrs, parent) for tag, attrs, parent in self.tags if tag == "svg"]
        self.assertEqual(len(icons), 1)
        attrs, parent = icons[0]
        self.assertEqual(parent, "a")
        self.assertEqual(attrs.get("aria-hidden"), "true")
        self.assertEqual(attrs.get("focusable"), "false")

    def test_tools_button_floats_above_app_and_loading_note(self):
        fab = css_rule(self.css, ".tools-fab")
        note = css_rule(self.css, ".note")
        self.assertIsNotNone(fab)
        self.assertRegex(fab, r"position:\s*fixed")
        fab_z = int(re.search(r"z-index:\s*(\d+)", fab).group(1))
        note_z = int(re.search(r"z-index:\s*(\d+)", note).group(1))
        self.assertGreater(fab_z, note_z)
        # ค่าสำรองแบบไม่มี env() ต้องมาก่อน ไม่งั้นเบราว์เซอร์เก่าจะไม่มีตำแหน่ง right/bottom เลย
        for side in ("right", "bottom"):
            with self.subTest(side=side):
                plain = re.search(side + r":\s*16px;", fab)
                safe = re.search(side + r":\s*calc\(16px \+ env\(safe-area-inset-" + side + r", 0px\)\);", fab)
                self.assertIsNotNone(plain)
                self.assertIsNotNone(safe)
                self.assertLess(plain.start(), safe.start())

    def test_label_does_not_block_clicks_in_app(self):
        label = css_rule(self.css, ".tools-fab-label")
        self.assertIsNotNone(label)
        self.assertRegex(label, r"pointer-events:\s*none")

    def test_hover_styles_only_for_mouse_devices(self):
        # บนจอสัมผัส :hover ค้างหลังแตะ ปุ่มจะขยายค้างและป้ายชื่อบังเนื้อหา
        outside = re.sub(r"@media \(hover: hover\) \{(?:[^{}]*\{[^{}]*\})*\s*\}", "", self.css)
        self.assertNotEqual(outside, self.css, "ต้องมี @media (hover: hover)")
        self.assertNotRegex(outside, r"\.tools-fab:hover[^{,]*\{[^}]*(?:scale\(1\.|opacity:\s*1)")

    def test_existing_security_guards_kept(self):
        # กันหน้าถูกฝังในเว็บอื่น (clickjacking) และรับ postMessage เฉพาะจาก iframe ของ Apps Script
        self.assertIn("window.top !== window.self", self.script)
        self.assertIn(r"/^https:\/\/script\.google\.com\/macros\/s\/[A-Za-z0-9_-]+\/exec$/", self.script)
        self.assertIn(r"/^https:\/\/[a-z0-9.-]+\.googleusercontent\.com$/", self.script)
        self.assertNotIn("innerHTML =", self.script.replace('innerHTML = ""', ""))

    def test_no_invisible_characters_in_sources(self):
        # อักขระล่องหน (zero-width, bidi control, NBSP) ซ่อนโค้ดหรือทำให้ข้อความหลอกตาได้
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for name in files:
                if not name.endswith(SOURCE_EXTENSIONS):
                    continue
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                with self.subTest(file=os.path.relpath(path, ROOT)):
                    bad = sorted({"U+%04X" % ord(ch) for ch in text
                                  if (unicodedata.category(ch) in ("Cf", "Co", "Zl", "Zp")
                                      or (unicodedata.category(ch) == "Zs" and ch != " ")
                                      or (unicodedata.category(ch) == "Cc" and ch not in "\n\t"))})
                    self.assertEqual(bad, [], "เขียนเป็น \\uXXXX แทน")


if __name__ == "__main__":
    unittest.main()
