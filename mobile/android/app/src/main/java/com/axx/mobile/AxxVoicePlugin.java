package com.axx.mobile;

import android.Manifest;
import android.app.KeyguardManager;
import android.content.Context;
import android.media.MediaRecorder;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.view.WindowManager;
import androidx.lifecycle.Lifecycle;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import java.io.File;
import java.nio.file.Files;

@CapacitorPlugin(name="AxxVoice",permissions={@Permission(alias="microphone",strings={Manifest.permission.RECORD_AUDIO})})
public class AxxVoicePlugin extends Plugin {
    private final Handler handler=new Handler(Looper.getMainLooper());
    private MediaRecorder recorder;
    private String sessionId="",state="idle",reason="";
    private long lastContact,started;
    private File audioFile;

    @Override public void load(){
        audioFile=new File(getContext().getFilesDir(),"remote-voice.m4a");
        var saved=getContext().getSharedPreferences("axx_voice",Context.MODE_PRIVATE);
        sessionId=saved.getString("session","");
        if(!sessionId.isEmpty()){
            state=audioFile.isFile() && audioFile.length()>16?"stopped":"failed";
            reason="process_interrupted";
        }
    }
    static void validateStart(String session,int seconds){
        if(session==null || !session.matches("[a-f0-9-]{36}") || seconds<5 || seconds>55)
            throw new IllegalArgumentException("Invalid voice session or limit");
    }
    private boolean visible(){
        return getActivity().getLifecycle().getCurrentState().isAtLeast(Lifecycle.State.RESUMED)
            && getContext().getSystemService(PowerManager.class).isInteractive()
            && !getContext().getSystemService(KeyguardManager.class).isKeyguardLocked();
    }
    private JSObject snapshot(){
        JSObject result=new JSObject();
        result.put("session_id",sessionId);result.put("state",state);result.put("reason",reason);
        result.put("visible",visible());result.put("permission",getPermissionState("microphone")==PermissionState.GRANTED?"granted":getPermissionState("microphone")==PermissionState.PROMPT?"prompt":"denied");
        int amplitude=0;
        if(recorder!=null)try{amplitude=recorder.getMaxAmplitude();}catch(RuntimeException ignored){}
        result.put("level",Math.min(1.0,amplitude/32767.0));
        result.put("elapsed_seconds",recorder==null?0:(SystemClock.elapsedRealtime()-started)/1000);
        result.put("bytes",audioFile==null?0:audioFile.length());return result;
    }
    private void emit(){notifyListeners("captureState",snapshot());}
    private void stopCapture(String why){
        if(recorder==null)return;
        MediaRecorder current=recorder;recorder=null;
        try{current.stop();state="stopped";reason=why;}
        catch(RuntimeException error){state="failed";reason="Could not finalize audio. Try again.";}
        finally{
            current.release();handler.removeCallbacks(watchdog);
            getActivity().getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            emit();
        }
    }
    private final Runnable watchdog=new Runnable(){public void run(){
        if(recorder==null)return;
        if(!visible())stopCapture("background");
        else if(getPermissionState("microphone")!=PermissionState.GRANTED)stopCapture("permission_revoked");
        else if(SystemClock.elapsedRealtime()-lastContact>8000)stopCapture("connection_lost");
        else handler.postDelayed(this,500);
    }};
    @PluginMethod public void status(PluginCall call){handler.post(()->call.resolve(snapshot()));}
    @PluginMethod public void permit(PluginCall call){
        if(getPermissionState("microphone")==PermissionState.GRANTED){call.resolve(snapshot());return;}
        requestPermissionForAlias("microphone",call,"permissionResult");
    }
    @PermissionCallback private void permissionResult(PluginCall call){call.resolve(snapshot());}
    @PluginMethod public void start(PluginCall call){handler.post(()->{
        if(!sessionId.isEmpty() && !sessionId.equals(call.getString("session_id",""))){call.reject("Review or discard the previous audio before starting another session.");return;}
        try{
            String requested=call.getString("session_id","");int seconds=call.getInt("max_seconds",30);
            validateStart(requested,seconds);
            if(!visible())throw new IllegalStateException("Open Axx Mobile to use the remote microphone.");
            if(getPermissionState("microphone")!=PermissionState.GRANTED)throw new IllegalStateException("Explicitly allow microphone access in Axx Mobile.");
            if(sessionId.equals(requested)){call.resolve(snapshot());return;}
            if(!sessionId.isEmpty())throw new IllegalStateException("Review or discard the previous audio before starting another session.");
            sessionId=requested;reason="";
            if(!getContext().getSharedPreferences("axx_voice",Context.MODE_PRIVATE).edit().putString("session",sessionId).commit())throw new IllegalStateException("Could not save the session");
            recorder=new MediaRecorder();
            recorder.setAudioSource(MediaRecorder.AudioSource.MIC);
            recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
            recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
            recorder.setAudioChannels(1);recorder.setAudioSamplingRate(16000);recorder.setAudioEncodingBitRate(64000);
            recorder.setOutputFile(audioFile.getAbsolutePath());recorder.setMaxDuration(seconds*1000);
            recorder.setMaxFileSize(1400*1024);
            recorder.setOnInfoListener((r,what,extra)->{if(what==MediaRecorder.MEDIA_RECORDER_INFO_MAX_DURATION_REACHED || what==MediaRecorder.MEDIA_RECORDER_INFO_MAX_FILESIZE_REACHED)stopCapture("timeout");});
            recorder.setOnErrorListener((r,what,extra)->stopCapture("recorder_error"));
            recorder.prepare();recorder.start();state="recording";started=lastContact=SystemClock.elapsedRealtime();
            getActivity().getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            handler.postDelayed(watchdog,500);emit();call.resolve(snapshot());
        }catch(Exception error){
            if(recorder!=null){recorder.release();recorder=null;}
            handler.removeCallbacks(watchdog);
            getActivity().getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            state=sessionId.isEmpty()?"idle":"failed";reason=error.getMessage();emit();call.reject(reason);
        }
    });}
    @PluginMethod public void heartbeat(PluginCall call){handler.post(()->{lastContact=SystemClock.elapsedRealtime();call.resolve();});}
    @PluginMethod public void stop(PluginCall call){handler.post(()->{
        if(!sessionId.equals(call.getString("session_id",""))){call.reject("Capture session does not match");return;}
        stopCapture(call.getBoolean("from_pc",false)?"pc_stop":"user_stop");call.resolve(snapshot());
    });}
    @PluginMethod public void audio(PluginCall call){handler.post(()->{
        try{
            if(!sessionId.equals(call.getString("session_id","")) || !state.equals("stopped"))throw new IllegalStateException("Audio capture has not finished");
            if(audioFile.length()<16 || audioFile.length()>1400*1024)throw new IllegalStateException("Audio exceeds the allowed size");
            byte[] bytes=Files.readAllBytes(audioFile.toPath());JSObject result=new JSObject();
            result.put("session_id",sessionId);result.put("mime","audio/mp4");result.put("audio_base64",java.util.Base64.getEncoder().encodeToString(bytes));call.resolve(result);
        }catch(Exception error){call.reject(error.getMessage());}
    });}
    @PluginMethod public void discard(PluginCall call){handler.post(()->{
        if(!sessionId.equals(call.getString("session_id",""))){call.reject("Capture session does not match");return;}
        stopCapture("cancelled");
        if(audioFile.exists() && !audioFile.delete()){call.reject("Could not delete local audio");return;}
        if(!getContext().getSharedPreferences("axx_voice",Context.MODE_PRIVATE).edit().clear().commit()){call.reject("Could not close the session");return;}
        sessionId="";state="idle";reason="";emit();call.resolve();
    });}
    @Override protected void handleOnPause(){stopCapture("background");}
    @Override protected void handleOnDestroy(){stopCapture("activity_closed");handler.removeCallbacksAndMessages(null);}
}
