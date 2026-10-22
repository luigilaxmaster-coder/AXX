import base64
import hashlib
import io
from pathlib import Path
import tempfile
import time
import unittest

from PIL import Image
from pypdf import PdfReader, PdfWriter

from backend.converter import ConverterService


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = ConverterService(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def upload(self, files):
        job = self.service.new([{'name': name, 'size': len(data)} for name, data in files])
        for index, (_, data) in enumerate(files):
            for offset in range(0, len(data), 128 * 1024):
                self.service.upload(job['id'], index, offset, base64.b64encode(data[offset:offset + 128 * 1024]).decode())
        return self.service.probe(job['id'])

    def done(self, job, operation, options):
        self.service.run(job['id'], operation, options)
        for _ in range(100):
            result = self.service.status(job['id'])
            if result['state'] != 'running':
                self.assertEqual(result['state'], 'done', result['error'])
                return result
            time.sleep(.02)
        self.fail('Conversion did not finish')

    def test_png_to_jpeg_background_and_original(self):
        source = io.BytesIO()
        Image.new('RGBA', (2, 1), (255, 0, 0, 0)).save(source, format='PNG')
        data = source.getvalue()
        job = self.upload([('fake.pdf', data)])
        self.assertEqual(job['info'][0]['kind'], 'png')
        result = self.done(job, 'png-jpeg', {'background': '#00ff00', 'quality': 90})
        with Image.open(result['result']['path']) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.size, (2, 1))
            self.assertGreater(image.getpixel((0, 0))[1], 200)
        self.assertEqual(job['info'][0]['sha256'], hashlib.sha256(data).hexdigest())
        self.assertFalse((Path(job['output_directory']) / 'input-0').exists())

    def test_jpeg_to_png_applies_orientation(self):
        source = io.BytesIO()
        exif = Image.Exif(); exif[274] = 6
        Image.new('RGB', (3, 2), 'blue').save(source, format='JPEG', exif=exif)
        job = self.upload([('photo.jpg', source.getvalue())])
        result = self.done(job, 'jpeg-png', {})
        with Image.open(result['result']['path']) as image:
            self.assertEqual(image.format, 'PNG')
            self.assertEqual(image.size, (2, 3))

    def pdf(self, sizes):
        writer = PdfWriter()
        for width, height in sizes:
            writer.add_blank_page(width=width, height=height)
        stream = io.BytesIO(); writer.write(stream)
        return stream.getvalue()

    def test_merge_and_extract_preserve_order_and_sizes(self):
        first = self.pdf([(100, 200)])
        second = self.pdf([(300, 400), (500, 600)])
        job = self.upload([('first.pdf', first), ('second.pdf', second)])
        merged = self.done(job, 'pdf-merge', {})
        with Path(merged['result']['path']).open('rb') as stream:
            reader = PdfReader(stream)
            self.assertEqual([(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages], [(100, 200), (300, 400), (500, 600)])
        extract_job = self.upload([('second.pdf', second)])
        extracted = self.done(extract_job, 'pdf-extract', {'pages': '1, 2'})
        with Path(extracted['result']['path']).open('rb') as stream:
            self.assertEqual(len(PdfReader(stream).pages), 2)
        self.assertFalse((Path(job['output_directory']) / 'input-0').exists())

    def test_invalid_range_does_not_publish(self):
        job = self.upload([('pages.pdf', self.pdf([(100, 100)]))])
        with self.assertRaises(ValueError):
            self.service.run(job['id'], 'pdf-extract', {'pages': '0, 1'})
        self.assertEqual(self.service.status(job['id'])['state'], 'ready')
        self.assertEqual(list(Path(job['output_directory']).glob('*.pdf')), [])

    def test_cancelled_upload_removes_copy_and_cannot_run(self):
        data = self.pdf([(100, 100)])
        job = self.service.new([{'name':'plan.pdf', 'size':len(data)}])
        self.service.upload(job['id'], 0, 0, base64.b64encode(data).decode())
        self.assertEqual(self.service.cancel(job['id'])['state'], 'cancelled')
        self.assertFalse((Path(job['output_directory']) / 'input-0').exists())
        with self.assertRaises(ValueError):
            self.service.probe(job['id'])

    def test_restart_discards_partial_upload_and_reports_interruption(self):
        data = self.pdf([(100, 100)])
        job = self.service.new([{'name':'plan.pdf', 'size':len(data)}])
        self.service.upload(job['id'], 0, 0, base64.b64encode(data[:20]).decode())
        (Path(job['output_directory']) / 'unido.pdf').write_bytes(data)
        restarted = ConverterService(self.temp.name)
        self.assertFalse((Path(job['output_directory']) / 'input-0').exists())
        self.assertFalse((Path(job['output_directory']) / 'unido.pdf').exists())
        self.assertEqual(restarted.history()['incomplete'][0]['state'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
