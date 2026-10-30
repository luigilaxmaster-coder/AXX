package com.axx.mobile;

import org.junit.Test;
import static org.junit.Assert.*;

public class TransportTest {
    @Test public void controlTimeoutCoversTheNativeAcknowledgementBudget() {
        assertTrue(AxxTransportPlugin.readTimeout("/v1/control/acquire","POST") >= 3000+2000);
        for (String operation : new String[]{"events","renew","release","status"}) {
            int timeout=AxxTransportPlugin.readTimeout("/v1/control/"+operation,"POST");
            assertTrue(timeout > 2000);
            assertTrue(timeout < 3000);
        }
        assertTrue(500+AxxTransportPlugin.readTimeout("/v1/control/renew","POST") < 3000);
        assertEquals(8000,AxxTransportPlugin.readTimeout("/v1/snapshot","GET"));
        assertEquals(75000,AxxTransportPlugin.readTimeout("/v1/transfers/chunk","POST"));
        assertEquals(1500,AxxTransportPlugin.readTimeout("/v1/avatar/gesture","POST"));
    }
    @Test public void pairingLinksRejectAmbiguousOrUnsafeIdentity() throws Exception {
        String link="axx://pair?endpoint=https%3A%2F%2F192.168.0.10%3A4443&fingerprint="+"a".repeat(64)+"&code="+"b".repeat(32);
        assertEquals("https://192.168.0.10:4443",AxxTransportPlugin.pairingFields(link).get("endpoint"));
        for(String bad:new String[]{link+"&code=duplicate",link+"#fragment",link.replace("axx://pair?","axx://user@pair?"),link.replace("axx://pair?","axx://pair/path?"),link.replace("192.168.0.10","8.8.8.8"),link.replace("a".repeat(64),"short"),link+"&",link.replace("b".repeat(32),"short")}) {
            try { AxxTransportPlugin.pairingFields(bad); fail("Unsafe pairing accepted"); }
            catch(IllegalArgumentException expected) {}
        }
    }
    @Test public void shortcutRejectsNonPngAndUnboundedDimensions() {
        for (String value : new String[]{"", "data:image/jpeg;base64,AAAA", "data:image/png;base64,AAAA"}) {
            try { AxxTransportPlugin.shortcutPng(value); fail("Invalid image accepted"); }
            catch (IllegalArgumentException expected) {}
        }
        byte[] bytes=new byte[24];
        byte[] signature={(byte)137,80,78,71,13,10,26,10};System.arraycopy(signature,0,bytes,0,8);
        java.nio.ByteBuffer.wrap(bytes).putInt(16,4096).putInt(20,4096);
        try { AxxTransportPlugin.shortcutPng("data:image/png;base64,"+java.util.Base64.getEncoder().encodeToString(bytes));fail("Oversized image accepted"); }
        catch (IllegalArgumentException expected) {}
    }
    @Test public void changedCertificateIdentityIsRejected() throws Exception {
        var input = getClass().getResourceAsStream("/test-host.pem");
        assertNotNull(input);
        java.security.cert.X509Certificate certificate;
        try (input) { certificate = (java.security.cert.X509Certificate) java.security.cert.CertificateFactory.getInstance("X.509").generateCertificate(input); }
        StringBuilder pin = new StringBuilder();
        for (byte value : java.security.MessageDigest.getInstance("SHA-256").digest(certificate.getEncoded())) pin.append(String.format("%02x", value));
        AxxTransportPlugin.checkPin(certificate, pin.toString());
        try { AxxTransportPlugin.checkPin(certificate, "0".repeat(64)); fail("Changed certificate accepted"); }
        catch (java.security.cert.CertificateException expected) {}
    }
    @Test public void onlyExplicitPrivateHttpsEndpointsAreAccepted() throws Exception {
        assertEquals("192.168.0.10", AxxTransportPlugin.validateEndpoint("https://192.168.0.10:4443").getHost());
        assertEquals("100.64.0.0", AxxTransportPlugin.validateEndpoint("https://100.64.0.0:4443").getHost());
        assertEquals("100.127.255.255", AxxTransportPlugin.validateEndpoint("https://100.127.255.255:4443").getHost());
        for (String value : new String[]{"http://192.168.0.10:4443", "https://127.0.0.1:4443", "https://8.8.8.8:443", "https://evil.example:443", "https://192.168.0.10:4443/other", "https://user@192.168.0.10:4443", "https://192.168.0.10:4443?redirect=1", "https://192.168.000.10:4443", "https://192.168.0.10:65536", "https://100.63.255.255:4443", "https://100.128.0.0:4443", "https://100.255.0.1:4443"}) {
            try { AxxTransportPlugin.validateEndpoint(value); fail("Accepted unsafe endpoint: " + value); }
            catch (IllegalArgumentException expected) {}
        }
    }
    @Test public void queuedPrivateOperationsKeepTheirOriginalPcIdentity() {
        String device = "01234567-89ab-cdef-0123-456789abcdef", pin = "a".repeat(64);
        AxxTransportPlugin.checkExpectedIdentity(device, pin, device, pin);
        AxxTransportPlugin.checkExpectedIdentity(device, pin, null, null);
        for (String[] expected : new String[][]{{"different-device", pin}, {device, "b".repeat(64)}, {device, null}, {null, pin}}) {
            try { AxxTransportPlugin.checkExpectedIdentity(device, pin, expected[0], expected[1]); fail("Changed or incomplete identity accepted"); }
            catch (IllegalStateException correct) {}
        }
    }
}
