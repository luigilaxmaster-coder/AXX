import unittest
from playwright.sync_api import sync_playwright, expect
from mobile.tests import test_companion_ui as companion


class PersonalizationTests(unittest.TestCase):
    open = companion.CompanionUI.open
    def test_snapshot_camera_correction_is_smooth_wrapped_and_respects_direct_input(self):
        with sync_playwright() as p:
            page=self.open(p)
            result=page.evaluate('''()=>{
              const r=axxMobileRenderer;r.stop();r.configure({...r.settings,reducedMotion:false,staticMode:false});r.setStudio({living:true,autoRotate:false});
              r.cameraInitialized=false;r.setCamera20([0,0]);r.setCamera20([1.2,.4]);const immediate=r.angle.slice();
              let maxStep=0;for(let i=0;i<60;i++){const before=r.angle[0];r.advanceMotion(1/60);maxStep=Math.max(maxStep,Math.abs(r.angle[0]-before));}
              const settled=r.angle.slice();r.setCamera20([2*Math.PI-.02,0]);const wrapped=r.cameraCorrection[0];
              r.rotate(.1,.1);const touchCleared=r.cameraCorrection===null;
              const beforeInvalid=r.angle.slice();r.setCamera20([NaN,Infinity]);const invalidIgnored=JSON.stringify(beforeInvalid)===JSON.stringify(r.angle);
              r.configure({...r.settings,reducedMotion:true});r.setCamera20([.7,.2]);
              return {immediate,maxStep,settled,wrapped,touchCleared,invalidIgnored,reduced:r.angle.slice(),noReducedAnimation:r.cameraCorrection===null};
            }''')
            self.assertEqual(result['immediate'],[0,0])
            self.assertLess(result['maxStep'],.3)
            self.assertAlmostEqual(result['settled'][0],1.2,delta=.001)
            self.assertAlmostEqual(result['settled'][1],.4,delta=.001)
            self.assertLess(abs(result['wrapped']),1.3)
            self.assertTrue(result['touchCleared'])
            self.assertTrue(result['invalidIgnored'])
            self.assertEqual(result['reduced'],[.7,.2])
            self.assertTrue(result['noReducedAnimation'])

    def test_gpu_respects_shared_hidden_canvas_and_restores_visible_pixels(self):
        with sync_playwright() as p:
            page=self.open(p)
            result=page.evaluate('''()=>{
              const r=axxMobileRenderer;r.stop();r.draw(1);const before=r.pixelSummary().solid;
              r.setHidden(true);const hidden=r.pixelSummary().solid,hit=r.hitTest(0,0);
              r.setHidden(false);r.draw(1);
              return {before,hidden,hit,restored:r.pixelSummary().solid,mode:r.diagnostics().mode};
            }''')
            self.assertGreater(result['before'],0)
            self.assertEqual(result['hidden'],0)
            self.assertFalse(result['hit'])
            self.assertGreater(result['restored'],0)
            self.assertEqual(result['mode'],'gpu')

    def test_theme_and_accent_persist_and_keep_readable_foregrounds(self):
        with sync_playwright() as p:
            page=self.open(p,339);page.locator('#character-options').click()
            page.locator('[data-mobile-theme=dark]').click()
            expect(page.locator('html')).to_have_attribute('data-theme','dark')
            for accent in ['#ffffff','#000000','#7955dd']:
                page.locator('#accent-color').fill(accent)
                page.locator('#accent-color').dispatch_event('change')
                expect(page.locator('#accent-color')).to_be_enabled()
                self.assertEqual(page.locator('#accent-color').input_value(),accent)
                ratios=page.evaluate('''()=>{
                  const css=getComputedStyle(document.documentElement),rgb=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
                  const lum=hex=>rgb(hex).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
                  const ratio=(a,b)=>(Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05),get=name=>css.getPropertyValue('--mobile-'+name).trim();
                  return [ratio(get('accent'),get('on-accent')),ratio(get('accent-text'),get('bg'))];
                }''')
                self.assertTrue(all(value>=4.5 for value in ratios),ratios)
            page.reload();expect(page.locator('html')).to_have_attribute('data-theme','dark')
            self.assertEqual(page.locator('#accent-color').input_value(),'#7955dd')
            page.locator('#character-options').click();page.locator('[data-mobile-theme=light]').click()
            expect(page.locator('html')).to_have_attribute('data-theme','light')

    def test_native_theme_error_does_not_save_a_false_selection(self):
        with sync_playwright() as p:
            page=self.open(p);page.locator('#character-options').click()
            page.evaluate('()=>{Capacitor.Plugins.AxxTransport.appearance=async()=>{throw Error("No se guardó");};}')
            page.locator('[data-mobile-theme=dark]').click()
            expect(page.locator('#display-feedback')).to_contain_text('No se pudo guardar')
            self.assertEqual(page.locator('html').get_attribute('data-theme'),'light')

    def test_storage_failure_restores_the_native_theme(self):
        with sync_playwright() as p:
            page=self.open(p);page.locator('#character-options').click()
            page.evaluate('''()=>{window.nativeTheme='light';Capacitor.Plugins.AxxTransport.appearance=async a=>{nativeTheme=a.theme;};
              const old=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k==='axx.mobile.display')throw Error('Storage full');return old.call(this,k,v);};}''')
            page.locator('[data-mobile-theme=dark]').click()
            expect(page.locator('#display-feedback')).to_contain_text('No se pudo guardar')
            expect(page.locator('[data-mobile-theme=dark]')).to_be_enabled()
            self.assertEqual(page.evaluate('nativeTheme'),'light')
            self.assertEqual(page.locator('html').get_attribute('data-theme'),'light')

    def test_character_waits_for_pc_receipt_and_snapshot_without_replay(self):
        with sync_playwright() as p:
            page=self.open(p)
            page.evaluate('''()=>{snapshot.capabilities={avatar_customization:true};scopes=['query','input.control'];window.edits=[];window.avatarResult={state:'queued'};
              const old=Capacitor.Plugins.AxxTransport.request;
              Capacitor.Plugins.AxxTransport.request=async a=>{
                if(a.path==='/v1/avatar/customize'){edits.push(a.body);return {data:avatarResult};}
                if(a.path.startsWith('/v1/avatar/operation'))return {data:avatarResult};
                return old(a);
              };}''')
            page.locator('#refresh').click();page.locator('#character-options').click()
            expect(page.locator('#character-palette')).to_be_enabled()
            page.locator('#character-palette').select_option('2')
            expect(page.locator('#character-palette')).to_be_disabled()
            self.assertEqual(page.evaluate('edits.length'),1)
            self.assertEqual(page.evaluate('edits[0].inputs'),{'action':'settings','palette':2})
            page.evaluate('avatarResult={state:"succeeded",postconditions_passed:true,output:{palette:2,form:3,finish:"prism"}}')
            expect(page.locator('#character-status')).to_contain_text('Guardado en tu PC')
            self.assertTrue(page.locator('#character-palette').is_disabled())
            page.evaluate('snapshot.appearance.settings.palette=2')
            page.locator('#character-close').click();page.locator('#refresh').click();page.locator('#character-options').click()
            expect(page.locator('#character-palette')).to_be_enabled()
            self.assertEqual(page.locator('#character-palette').input_value(),'2')
            self.assertEqual(page.evaluate('edits.length'),1)

    def test_gpu_matches_desktop_geometry_and_keeps_a_software_fallback(self):
        with sync_playwright() as p:
            page=self.open(p)
            result=page.evaluate('''()=>{
              const settings=Axx.normalizeSettings({...Axx.DEFAULT_SETTINGS,form:19,palette:2,scale:1,quality:'eco',reducedMotion:true,staticMode:true});const images=[];
              for(const Type of [Axx.SoftwareRenderer,Axx.MobileRenderer]){
                const host=document.createElement('div'),canvas=document.createElement('canvas');host.style.width='240px';host.style.height='240px';canvas.style.width='240px';canvas.style.height='240px';host.append(canvas);document.body.append(host);
                const r=new Type(canvas,settings);r.setForm(19,true);r.setStudio({living:false});r.setFinish('prism');r.draw(0);
                images.push({mode:r.diagnostics().mode,data:r.ctx.getImageData(0,0,canvas.width,canvas.height).data});
                if(Type===Axx.MobileRenderer){r.accelerated=false;r.draw(0);if(!r.pixelSummary().solid)throw Error('Empty CPU fallback');}
                r.stop();r.observer?.disconnect();host.remove();
              }
              const a=images[0].data,b=images[1].data;let intersection=0,union=0,error=0,n=0;
              for(let i=0;i<a.length;i+=4){if(a[i+3]>16||b[i+3]>16)union++;if(a[i+3]>16&&b[i+3]>16)intersection++;if(a[i+3]===255&&b[i+3]===255){n+=3;for(let k=0;k<3;k++)error+=Math.abs(a[i+k]-b[i+k]);}}
              return {mode:images[1].mode,iou:intersection/union,error:error/n};
            }''')
            self.assertEqual(result['mode'],'gpu')
            self.assertGreater(result['iou'],.97)
            self.assertLess(result['error'],3)

    def test_cached_droplets_keep_exact_pixels_and_stop_repeating_base_geometry(self):
        with sync_playwright() as p:
            page=self.open(p)
            result=page.evaluate('''()=>{
              const host=document.createElement('div'),canvas=document.createElement('canvas');
              host.style.cssText='position:fixed;left:-10000px;width:160px;height:160px';canvas.style.cssText='width:160px;height:160px';host.append(canvas);document.body.append(host);
              const r=new Axx.MobileRenderer(canvas,Axx.normalizeSettings({...Axx.DEFAULT_SETTINGS,quality:'balanced'}));
              const optimized=r.droplets,legacy=Axx.SoftwareRenderer.prototype.droplets,shape=Axx.softwareShape;
              let calls=0,changedBytes=0,cases=0;
              try{
                r.setForm(11,true);Axx.softwareShape=(...args)=>{calls++;return shape(...args);};
                r.project=()=>{};r.droplets();const first=calls;r.droplets();const repeated=calls-first;
                delete r.project;Axx.softwareShape=shape;
                for(let form=0;form<24;form++)for(const finish of ['obsidian','prism','smoke'])for(const view of form===11?[0,1,2,3]:[0]){
                  r.setStudio({view});r.setForm(form,true);r.setFinish(finish);r.configure({...r.settings,palette:form%9});r.setState(form%2?'thinking':'idle');r.advanceMotion(.016);
                  r.droplets=legacy;r.draw(1);const before=r.ctx.getImageData(0,0,canvas.width,canvas.height).data;
                  r.droplets=optimized;r.draw(1);const after=r.ctx.getImageData(0,0,canvas.width,canvas.height).data;
                  for(let i=0;i<before.length;i++)if(before[i]!==after[i])changedBytes++;
                  cases++;
                }
                return {first,repeated,expected:(r.bead.u+1)*(r.bead.v+1),changedBytes,cases,mode:r.diagnostics().mode,quality:r.settings.quality,adaptive:r.adaptive};
              }finally{Axx.softwareShape=shape;r.stop();r.observer?.disconnect();r.gl?.getExtension('WEBGL_lose_context')?.loseContext();host.remove();}
            }''')
            self.assertEqual(result['mode'],'gpu')
            self.assertEqual(result['first'],result['expected'])
            self.assertEqual(result['repeated'],0)
            self.assertEqual(result['cases'],81)
            self.assertEqual(result['changedBytes'],0)
            self.assertEqual(result['quality'],'balanced')
            self.assertEqual(result['adaptive'],1)
