//! Separate desktop surfaces: selection receives input; the recording halo passes it through.
use serde::{Deserialize, Serialize};
use std::sync::{Mutex, mpsc};
use std::time::Duration;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder, PhysicalPosition, PhysicalSize};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
pub struct Region { pub x:i32, pub y:i32, pub width:u32, pub height:u32 }
struct Selection { token:String, bounds:Region, tx:mpsc::Sender<Option<Region>> }
static SELECTION: Mutex<Option<Selection>> = Mutex::new(None);

pub fn selector_closed() {
    if let Some(selection) = SELECTION.lock().unwrap().take() {
        let _ = selection.tx.send(None);
    }
}

fn require_main(window:&WebviewWindow)->Result<(),String>{if window.label()=="main" {Ok(())} else {Err("Only the main window can start capture".into())}}
fn close(app:&AppHandle,label:&str){if let Some(w)=app.get_webview_window(label){let _=w.destroy();}}
fn protect(w:&WebviewWindow)->Result<(),String>{
    #[cfg(windows)] unsafe {
        let hwnd=w.hwnd().map_err(|e|e.to_string())?;
        if windows_sys::Win32::UI::WindowsAndMessaging::SetWindowDisplayAffinity(hwnd.0 as _,0x11)==0 {return Err("Windows no pudo excluir el halo del vídeo".into());}
    }
    Ok(())
}
fn bounds()->Region {
    #[cfg(windows)] unsafe {
        use windows_sys::Win32::UI::WindowsAndMessaging::GetSystemMetrics;
        Region{x:GetSystemMetrics(76),y:GetSystemMetrics(77),width:GetSystemMetrics(78) as u32,height:GetSystemMetrics(79) as u32}
    }
    #[cfg(not(windows))] {Region{x:0,y:0,width:0,height:0}}
}
fn normalized(rect:[f64;4],b:Region)->Result<Region,String>{
    if rect.iter().any(|v|!v.is_finite()||*v<0.0||*v>1.0)||rect[0]+rect[2]>1.000001||rect[1]+rect[3]>1.000001 {return Err("Área inválida".into());}
    let width=(rect[2]*b.width as f64).floor() as u32;
    let height=(rect[3]*b.height as f64).floor() as u32;
    if width<16||height<16||width>7680||height>4320{return Err("Selecciona un área entre 16 × 16 y 7680 × 4320 píxeles".into());}
    Ok(Region{x:b.x+(rect[0]*b.width as f64).floor() as i32,y:b.y+(rect[1]*b.height as f64).floor() as i32,width:width-width%2,height:height-height%2})
}
fn surface(app:&AppHandle,label:&str,url:String,region:Region,interactive:bool)->Result<WebviewWindow,String>{
    let w=WebviewWindowBuilder::new(app,label,WebviewUrl::App(url.into()))
        .title("Axx · área de grabación").transparent(true).decorations(false).shadow(false)
        .always_on_top(true).skip_taskbar(true).resizable(false).visible(false).focused(interactive)
        .build().map_err(|e|e.to_string())?;
    let setup=(||{
        w.set_position(PhysicalPosition::new(region.x,region.y)).map_err(|e|e.to_string())?;
        w.set_size(PhysicalSize::new(region.width,region.height)).map_err(|e|e.to_string())?;
        protect(&w)?;
        w.set_ignore_cursor_events(!interactive).map_err(|e|e.to_string())?;
        w.show().map_err(|e|e.to_string())?;
        if interactive {w.set_focus().map_err(|e|e.to_string())?;}
        Ok::<(),String>(())
    })();
    if let Err(e)=setup{let _=w.destroy();return Err(e);}
    Ok(w)
}

#[tauri::command]
pub async fn capture_select(app:AppHandle,window:WebviewWindow)->Result<Option<Region>,String>{
    require_main(&window)?;
    let token=uuid::Uuid::new_v4().to_string();let b=bounds();let (tx,rx)=mpsc::channel();
    {
        let mut selection=SELECTION.lock().unwrap();
        if selection.is_some(){return Err("Ya hay una selección abierta".into());}
        if b.width==0||b.height==0{return Err("Escritorio no disponible".into());}
        *selection=Some(Selection{token:token.clone(),bounds:b,tx});
    }
    let url=format!("capture-overlay.html?mode=select&token={token}&width={}&height={}",b.width,b.height);
    if let Err(e)=surface(&app,"capture-selector",url,b,true){SELECTION.lock().unwrap().take();return Err(e);}
    let result=tauri::async_runtime::spawn_blocking(move||rx.recv_timeout(Duration::from_secs(180))).await.map_err(|e|e.to_string())?;
    // Ignore a stale completion if a later selection has already replaced it.
    let mut selection=SELECTION.lock().unwrap();
    if selection.as_ref().is_some_and(|s|s.token==token){selection.take();close(&app,"capture-selector");}
    result.map_err(|_|"La selección caducó; vuelve a intentarlo".into())
}
#[tauri::command]
pub fn capture_selection_finish(app:AppHandle,window:WebviewWindow,token:String,rect:Option<[f64;4]>)->Result<(),String>{
    if window.label()!="capture-selector"{return Err("Invalid selection window".into());}
    let mut selection=SELECTION.lock().unwrap();let active=selection.as_ref().ok_or("La selección terminó")?;
    if active.token!=token{return Err("La selección caducó".into());}
    let region=rect.map(|r|normalized(r,active.bounds)).transpose()?;
    let _=active.tx.send(region);selection.take();close(&app,"capture-selector");Ok(())
}
#[tauri::command]
pub fn capture_cancel_selection(app:AppHandle,window:WebviewWindow)->Result<(),String>{
    require_main(&window)?;if let Some(s)=SELECTION.lock().unwrap().take(){let _=s.tx.send(None);}
    close(&app,"capture-selector");Ok(())
}
#[tauri::command]
pub async fn capture_halo(app:AppHandle,window:WebviewWindow,region:Option<Region>,phase:String)->Result<(),String>{
    require_main(&window)?;
    if !["running","paused","countdown","stopping"].contains(&phase.as_str()) {close(&app,"capture-halo");return Ok(());}
    let r=region.ok_or("Falta el área")?;let b=bounds();
    if r.width<16||r.height<16||r.x<b.x||r.y<b.y||r.x as i64+r.width as i64>b.x as i64+b.width as i64||r.y as i64+r.height as i64>b.y as i64+b.height as i64{return Err("Área fuera del escritorio".into());}
    if crate::magic_pen::BUSY.load(std::sync::atomic::Ordering::Acquire) {
        return Err("Espera a que termine la captura de Magic Pen antes de cambiar el halo".into());
    }
    protect(&window)?;
    let halo=if let Some(w)=app.get_webview_window("capture-halo"){w} else {surface(&app,"capture-halo","capture-overlay.html?mode=halo".into(),r,false)?};
    halo.set_position(PhysicalPosition::new(r.x,r.y)).map_err(|e|e.to_string())?;
    halo.set_size(PhysicalSize::new(r.width,r.height)).map_err(|e|e.to_string())?;
    // Phase is a closed enum; no user text is evaluated.
    halo.eval(&format!("document.documentElement.dataset.phase={}",serde_json::to_string(&phase).unwrap())).map_err(|e|e.to_string())?;
    Ok(())
}
#[cfg(test)] mod tests{
    use super::*;
    #[test]fn area_uses_physical_desktop_coordinates(){assert_eq!(normalized([0.25,0.1,0.25,0.5],Region{x:-1920,y:0,width:3840,height:1080}).unwrap(),Region{x:-960,y:108,width:960,height:540});}
    #[test]fn rejects_tiny_outside_and_nan(){let b=Region{x:0,y:0,width:1920,height:1080};for r in [[0.0,0.0,0.001,0.001],[0.9,0.0,0.5,0.5],[f64::NAN,0.0,0.5,0.5]]{assert!(normalized(r,b).is_err());}}
}
