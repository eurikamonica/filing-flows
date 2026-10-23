"""The Fair value view's chart CSS must leave Plotly's SVG layers alone (the 3D sensitivity charts): sized to the view's
860 px charts, a wide page shrank Plotly's hover layer and its labels drifted away from their boxes."""
import re
import unittest
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / 'docs' / 'fairvalue-view.js'


class PlotlyLayers(unittest.TestCase):
    def test_svg_rules_skip_plotly(self):
        css = JS.read_text(encoding='utf-8')
        rules = re.findall(r'(\.fv svg[^{]*)\{', css)
        self.assertTrue(rules)
        for sel in rules:
            if re.fullmatch(r'\.fv svg( text)?', sel.strip()):
                self.fail(f'unscoped rule {sel!r} reaches Plotly\'s SVG layers')


if __name__ == '__main__':
    unittest.main()
