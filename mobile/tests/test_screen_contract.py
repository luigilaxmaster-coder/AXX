"""Declared browser fixtures: viewport coverage is not native phone certification."""
import argparse
import json
import re
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
from mobile.tests.test_ui import ROOT
from mobile.tests.test_companion_ui import FIXTURE
from mobile.tests.test_control_ui import CONTROL_FIXTURE

PROJECT=Path(__file__).resolve().parents[2]
CONTRACT=json.loads((PROJECT/'mobile/companion-contract.json').read_text(encoding='utf-8'))
SCREEN_FIXTURE=FIXTURE+CONTROL_FIXTURE+'''
snapshot.appearance.studio.living=false;
Capacitor.Plugins.AxxFiles={capacity:async()=>({max_size:10737418240,free_bytes:8589934592}),list:async()=>({files:[]})};
const screenRequest=Capacitor.Plugins.AxxTransport.request;
Capacitor.Plugins.AxxTransport.request=async a=>a.path==='/v1/files/status'?{data:{max_size:10737418240,permissions:{read:false,write:false},transfers:[]}}:screenRequest(a);
'''

def open_page(browser, scale=1, theme='light', dpr=1, snapshot=None):
    context=browser.new_context(viewport={'width':390,'height':844},device_scale_factor=dpr,reduced_motion='reduce')
    page=context.new_page();page.set_default_timeout(7000)
    def serve(route):
        name=route.request.url.split('https://axx.test/',1)[1] or 'index.html'
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():route.abort();return
        if path.suffix=='.css':
            css=re.sub(r'(font-size:\s*|font:\s*)([\d.]+)px',lambda m:m[1]+str(float(m[2])*scale)+'px',path.read_text(encoding='utf-8'))
            route.fulfill(body=css,content_type='text/css')
        else:route.fulfill(path=str(path))
    page.route('https://axx.test/**',serve)
    setup=SCREEN_FIXTURE+f"localStorage.setItem('axx.mobile.display',JSON.stringify({{theme:{json.dumps(theme)},accent:'#2864df'}}));"
    if snapshot is not None:setup+='snapshot='+json.dumps(snapshot)+';scopes=snapshot.scopes;'
    page.add_init_script(setup);page.goto('https://axx.test/')
    page.locator('#sync-status[data-state=complete]').wait_for()
    return page

def reference_snapshot(page):
    selectors=['.app-header','.brand','.axx-stage-container','#character-options','#open-chat','.live-nav']
    return page.evaluate('''selectors=>Object.fromEntries(selectors.map(s=>{const e=document.querySelector(s),r=e.getBoundingClientRect(),c=getComputedStyle(e);return [s,{box:[r.x,r.y,r.width,r.height].map(x=>Math.round(x*100)/100),font:c.fontSize,color:c.color,background:c.backgroundColor,radius:c.borderRadius}]}))''',selectors)

def inspect_case(page, profile):
    page.set_viewport_size({'width':profile['width'],'height':profile['height']})
    issues=[]
    panes=page.locator('.live-nav [data-pane]').evaluate_all('(items)=>items.map(x=>x.dataset.pane)')
    def geometry(label):
        issues.extend(page.evaluate('''label=>{
          const problems=[],nav=document.querySelector('.live-nav'),bounds=nav.getBoundingClientRect();
          if(bounds.bottom>innerHeight+1||bounds.left<-.5||bounds.right>innerWidth+.5)problems.push(label+': navigation outside viewport');
          for(const b of nav.querySelectorAll('button')){
            const r=b.getBoundingClientRect(),text=b.querySelector('span')?.getBoundingClientRect();
            if(r.width<44||r.height<44)problems.push(label+': navigation target below 44 CSS px');
            if(text&&(text.left<r.left-.5||text.right>r.right+.5))problems.push(label+': navigation label overflows '+b.dataset.pane);
          }
          const pane=document.querySelector('.live-pane:not([hidden])');
          if(pane&&pane.scrollWidth>pane.clientWidth+1)problems.push(label+': pane has horizontal overflow');
          return problems;
        }''',label))
    for pane in panes:
        page.locator('[data-pane='+pane+']').click();geometry(pane)
    page.locator('[data-pane=axx]').click()
    button=page.locator('#open-chat').bounding_box()
    nav=page.locator('.live-nav').bounding_box()
    if not button or not nav or button['y']+button['height']>nav['y']+1:issues.append('home: chat entry outside the content area')
    page.locator('#character-options').click()
    if page.locator('#character-dialog').evaluate('(d)=>d.scrollWidth>d.clientWidth+1'):issues.append('character: horizontal overflow')
    page.locator('#character-close').click()
    page.locator('[data-pane=chat]').click();page.locator('#draft').fill('Contract draft');page.locator('#draft').focus()
    page.set_viewport_size({'width':profile['width'],'height':CONTRACT['keyboard_height']})
    geometry('keyboard')
    if page.evaluate('()=>document.querySelector("#send").getBoundingClientRect().bottom>document.querySelector(".live-nav").getBoundingClientRect().top+1'):issues.append('keyboard: composer overlaps navigation')
    if page.locator('#draft').input_value()!='Contract draft':issues.append('keyboard: draft lost')
    page.locator('#draft').blur();page.set_viewport_size({'width':profile['width'],'height':profile['height']})
    return sorted(set(issues))

def run_matrix(study=False):
    cases=[];profiles=CONTRACT['required_layouts']+(CONTRACT['study_layouts'] if study else [])
    scales=CONTRACT['text_scales'] if study else CONTRACT['release_text_scales']
    with sync_playwright() as p:
        browser=p.chromium.launch()
        for dpr in CONTRACT['device_pixel_ratios']:
            for scale in scales:
                for theme in CONTRACT['themes']:
                    page=open_page(browser,scale,theme,dpr)
                    try:
                        for profile in profiles:
                            issues=inspect_case(page,profile)
                            cases.append({'profile':profile['id'],'width':profile['width'],'height':profile['height'],'theme':theme,'text_scale':scale,'dpr':dpr,'issues':issues,'result':'FAIL' if issues else 'PASS'})
                    finally:page.context.close()
        browser.close()
    return {'kind':'browser fixtures; no physical phone claim','cases':cases,'passed':sum(not row['issues'] for row in cases),'failed':sum(bool(row['issues']) for row in cases)}

class ScreenContractTests(unittest.TestCase):
    def test_all_required_screen_keyboard_theme_text_and_density_cases(self):
        report=run_matrix()
        prior=json.loads((Path(__file__).parent/'fixtures/screen-failures-20261029.json').read_text(encoding='utf-8'))
        key=lambda row:tuple(row[k] for k in ('profile','width','height','theme','text_scale','dpr'))
        self.assertEqual(len(prior),24)
        self.assertTrue({key(row) for row in prior}<={key(row) for row in report['cases']})
        self.assertEqual(len(report['cases']),120)
        failures=[row for row in report['cases'] if row['issues']]
        self.assertFalse(failures,json.dumps(failures,ensure_ascii=False))

    def test_approved_portrait_geometry_colors_and_sizes_are_preserved(self):
        references=json.loads((Path(__file__).parent/'fixtures/approved-portrait-layout.json').read_text(encoding='utf-8'))
        with sync_playwright() as p:
            browser=p.chromium.launch()
            for row in references:
                with self.subTest(width=row['width'],scale=row['scale'],theme=row['theme']):
                    page=open_page(browser,row['scale'],row['theme'])
                    try:
                        page.set_viewport_size({'width':row['width'],'height':row['height']})
                        actual=reference_snapshot(page)
                        for selector,expected in row['snapshot'].items():
                            self.assertEqual({k:v for k,v in actual[selector].items() if k!='box'},{k:v for k,v in expected.items() if k!='box'},selector)
                            for before,after in zip(expected['box'],actual[selector]['box']):self.assertAlmostEqual(before,after,delta=1,msg=selector)
                    finally:page.context.close()
            browser.close()

    def test_v1_old_optional_and_unknown_additive_snapshots_keep_identity_and_draft(self):
        fixtures=json.loads((Path(__file__).parent/'fixtures/compatibility-v1.json').read_text(encoding='utf-8'))
        with sync_playwright() as p:
            browser=p.chromium.launch()
            for name,value in fixtures.items():
                with self.subTest(snapshot=name):
                    page=open_page(browser,snapshot=value)
                    try:
                        self.assertEqual(page.evaluate('axxMobileRenderer.settings.palette'),value['appearance']['settings']['palette'])
                        self.assertEqual(page.evaluate('axxMobileRenderer.finish'),value['appearance']['finish'])
                        page.locator('[data-pane=chat]').click();page.locator('#draft').fill('Kept across sync')
                        page.locator('#refresh').click()
                        self.assertEqual(page.locator('#draft').input_value(),'Kept across sync')
                    finally:page.context.close()
            browser.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',action='store_true')
    parser.add_argument('--output',type=Path,default=PROJECT/'build/screen-study-20261029.json')
    args=parser.parse_args()
    if args.study:
        report=run_matrix(study=True);args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'failed':report['failed'],'output':str(args.output)}))
    else:unittest.main(argv=['screen-contract'])
