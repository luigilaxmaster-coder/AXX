"""QR rendering shared by the real pairing route and packaged-build checks."""
import base64
import io
import json
from xml.etree import ElementTree


def pairing_qr_base64(uri: str) -> str:
    if not isinstance(uri, str) or not 1 <= len(uri) <= 2048:
        raise ValueError('Invalid QR content length')
    import qrcode
    from qrcode.image.svg import SvgPathFillImage
    image = qrcode.make(uri, image_factory=SvgPathFillImage, border=4)
    output = io.BytesIO()
    image.save(output)
    return base64.b64encode(output.getvalue()).decode('ascii')


def verify_qr_runtime() -> dict:
    # No gateway, pairing code, user state or network is created by this check.
    svg = base64.b64decode(pairing_qr_base64('Axx packaged QR rendering check'), validate=True)
    root = ElementTree.fromstring(svg)
    if root.tag != '{http://www.w3.org/2000/svg}svg' or not root.findall('{http://www.w3.org/2000/svg}path'):
        raise RuntimeError('QR renderer returned an empty or invalid SVG')
    return {'result': 'PASS', 'check': 'packaged_mobile_qr', 'svg_bytes': len(svg)}


if __name__ == '__main__':
    print(json.dumps(verify_qr_runtime()))
