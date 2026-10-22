package com.axx.mobile;
import org.junit.Test;
import static org.junit.Assert.fail;
public class VoiceTest {
    @Test public void captureAlwaysRequiresBoundedSession(){
        String session="12345678-1234-1234-1234-123456789abc";
        AxxVoicePlugin.validateStart(session,30);
        for(int seconds:new int[]{-1,0,4,56,100000}){
            try{AxxVoicePlugin.validateStart(session,seconds);fail("Unbounded recording accepted");}catch(IllegalArgumentException expected){}
        }
        try{AxxVoicePlugin.validateStart("",30);fail("Missing session accepted");}catch(IllegalArgumentException expected){}
    }
}
