import unittest
from backend.mobile.windows_input import contour_rgba,desktop_motion


class CursorMaterialTests(unittest.TestCase):
    def test_relative_motion_maps_negative_monitor_origin_without_extra_acceleration(self):
        monitors=[{'x':-1280,'y':0,'width':1280,'height':1024},{'x':0,'y':0,'width':1920,'height':1080}]
        x,y,ax,ay=desktop_motion(-20,300,40,-10,monitors)
        self.assertEqual((x,y),(20,290))
        self.assertEqual((ax*3200//65536-1280,ay*1080//65536),(20,290))
        x,y,ax,ay=desktop_motion(1919,1079,2000,2000,monitors)
        self.assertEqual((x,y),(1919,1079));self.assertLessEqual(ax,65535);self.assertLessEqual(ay,65535)
    def test_surface_uses_shared_rgb_and_leaves_click_point_clear(self):
        table=bytes([17,39,83,255])*(128*128)
        image=contour_rgba(table,48,glow=0)
        self.assertEqual(image.getpixel((24,24))[3],0)
        visible=[p for p in image.getdata() if p[3]]
        self.assertTrue(visible)
        self.assertTrue(all(p[:3]==(17,39,83) for p in visible))
        self.assertLess(len(visible),400)
        self.assertEqual(image.tobytes(),contour_rgba(table,48,glow=0).tobytes())

    def test_material_update_changes_surface_and_fade_retracts(self):
        a=bytes([17,39,83,255])*(128*128);b=bytes([93,42,12,255])*(128*128)
        self.assertNotEqual(contour_rgba(a,48).tobytes(),contour_rgba(b,48).tobytes())
        self.assertIsNone(contour_rgba(a,48,opacity=0).getbbox())
        self.assertNotEqual(contour_rgba(a,48).tobytes(),contour_rgba(a,48,drag=True).tobytes())
