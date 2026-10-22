"""Non-destructive native Windows target for physical Android input acceptance."""
import json
from pathlib import Path
import tkinter as tk

folder=Path(__file__).resolve().parents[1]/'evidence/mobile-20261022/remote-control'
root=tk.Tk();root.title('Axx · verificación de entrada remota');root.geometry('900x650+60+120')
root.configure(bg='#eeeeee')
tk.Label(root,text='Axx · destino de prueba de ratón y teclado',font=('Segoe UI',20),bg='#eeeeee').pack(pady=12)
tk.Label(root,text='Ventana local de prueba. No modifica documentos ni ejecuta comandos.',bg='#eeeeee').pack()
text=tk.Text(root,height=6,font=('Segoe UI',20));text.pack(fill='x',padx=30,pady=12)
clicks=tk.StringVar(value='Clics: 0');count=0;events=[]
def left():
 global count
 count+=1;clicks.set('Clics: '+str(count));events.append({'type':'left_click','count':count})
button=tk.Button(root,textvariable=clicks,command=left,font=('Segoe UI',16));button.pack()
canvas=tk.Canvas(root,height=220,bg='#d5d5d5');canvas.pack(fill='both',expand=True,padx=30,pady=12)
canvas.create_text(430,30,text='Arrastra aquí · scroll vertical y horizontal',font=('Segoe UI',16))
dot=canvas.create_oval(380,85,420,125,fill='#444444')
def capture(e):
 events.append({'type':str(e.type),'keysym':getattr(e,'keysym',''),'keycode':getattr(e,'keycode',0),'x':e.x_root,'y':e.y_root,'state':e.state,'delta':getattr(e,'delta',0),'num':str(getattr(e,'num',''))})
 if str(e.type)=='6' and e.state&256:canvas.coords(dot,e.x-20,e.y-20,e.x+20,e.y+20)
for event in ['<ButtonPress>','<ButtonRelease>','<KeyPress>','<KeyRelease>','<MouseWheel>','<B1-Motion>']:
 root.bind_all(event,capture,add='+')
def save():
 def rect(w):return {'x':w.winfo_rootx(),'y':w.winfo_rooty(),'width':w.winfo_width(),'height':w.winfo_height()}
 data={'text':text.get('1.0','end-1c'),'clicks':count,'events':events[-500:],'targets':{'text':rect(text),'button':rect(button),'canvas':rect(canvas)},'drag':canvas.coords(dot)}
 temp=folder/'target-state.tmp';temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(folder/'target-state.json')
 root.after(200,save)
root.after(200,save);root.mainloop()
