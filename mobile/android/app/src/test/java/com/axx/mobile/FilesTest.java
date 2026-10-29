package com.axx.mobile;

import org.junit.Test;
import static org.junit.Assert.*;

public class FilesTest {
    @Test public void rejectsUnsafeIdentifiersAndNames() {
        assertEquals("01234567-89ab-cdef-0123-456789abcdef", AxxFilesPlugin.checkedId("01234567-89ab-cdef-0123-456789abcdef"));
        assertEquals("Plano revisión.pdf", AxxFilesPlugin.checkedName("Plano revisión.pdf"));
        for (String id : new String[]{"../outside", "", "a", "01234567-89ab-cdef-0123-456789abcde/"}) {
            try { AxxFilesPlugin.checkedId(id); fail("Unsafe id accepted"); } catch (IllegalArgumentException expected) {}
        }
        for (String name : new String[]{"../outside", "a/b", "a\\b", "..", "\nfile", "", "x".repeat(181), "file.", "file ", "a:stream", "CON", "COM1.txt", "LPT².pdf", "NUL.dat", "a?b"}) {
            try { AxxFilesPlugin.checkedName(name); fail("Unsafe name accepted"); } catch (IllegalArgumentException expected) {}
        }
    }
    @Test public void validatesBoundsAndFinalBlock() {
        assertEquals(10L * 1024 * 1024 * 1024, AxxFilesPlugin.MAX_SIZE);
        AxxFilesPlugin.checkedManifest(0, "a".repeat(64), 262144);
        AxxFilesPlugin.checkedManifest(AxxFilesPlugin.MAX_SIZE, "a".repeat(64), 262144);
        assertEquals(262144, AxxFilesPlugin.expectedLength(262145, 0));
        assertEquals(1, AxxFilesPlugin.expectedLength(262145, 1));
        for (long size : new long[]{-1, AxxFilesPlugin.MAX_SIZE + 1}) {
            try { AxxFilesPlugin.checkedManifest(size, "a".repeat(64), 262144); fail("Invalid size accepted"); } catch (IllegalArgumentException expected) {}
        }
        for (String hash : new String[]{"", "a".repeat(63), "A".repeat(64), "x".repeat(64)}) {
            try { AxxFilesPlugin.checkedManifest(1, hash, 262144); fail("Invalid hash accepted"); } catch (IllegalArgumentException expected) {}
        }
        try { AxxFilesPlugin.checkedManifest(1, "a".repeat(64), 1); fail("Invalid chunk size accepted"); } catch (IllegalArgumentException expected) {}
        for (int index : new int[]{-1, 2, Integer.MAX_VALUE}) {
            try { AxxFilesPlugin.expectedLength(262145, index); fail("Invalid block accepted"); } catch (IllegalArgumentException expected) {}
        }
        try { AxxFilesPlugin.expectedLength(0, 0); fail("Empty file has no block"); } catch (IllegalArgumentException expected) {}
    }
    @Test public void reservesSpaceForEncryptionAndChecksOnlyRemainingBytes() {
        long reserve = 16L * 1024 * 1024;
        assertEquals(reserve, AxxFilesPlugin.storageBytes(0));
        assertEquals(reserve + 262144 + 8192, AxxFilesPlugin.storageBytes(262144));
        assertEquals(reserve + 262145 + 2 * 8192, AxxFilesPlugin.storageBytes(262145));
        long remaining = 262145, needed = AxxFilesPlugin.storageBytes(remaining);
        AxxFilesPlugin.checkAvailableSpace(remaining, needed);
        assertTrue(AxxFilesPlugin.storageBytes(remaining + 262144) > needed);
        for (long free : new long[]{-1, 0, needed - 1}) {
            try { AxxFilesPlugin.checkAvailableSpace(remaining, free); fail("Insufficient storage accepted"); }
            catch (IllegalStateException expected) {}
        }
        for (long size : new long[]{-1, AxxFilesPlugin.MAX_SIZE + 1, Long.MAX_VALUE}) {
            try { AxxFilesPlugin.storageBytes(size); fail("Unbounded storage estimate accepted"); }
            catch (IllegalArgumentException expected) {}
        }
        assertTrue(AxxFilesPlugin.storageBytes(AxxFilesPlugin.MAX_SIZE) > AxxFilesPlugin.MAX_SIZE);
        AxxFilesPlugin.checkAvailableSpace(AxxFilesPlugin.MAX_SIZE, Long.MAX_VALUE);
    }
    @Test public void encryptionRejectsTamperingAndWrongFileIdentity() throws Exception {
        javax.crypto.KeyGenerator generator = javax.crypto.KeyGenerator.getInstance("AES"); generator.init(256);
        javax.crypto.SecretKey key = generator.generateKey();
        byte[] aad = "transfer-id:block-0".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        byte[] clear = new byte[]{0, 1, 2, 3, 4};
        byte[] first = AxxFilesPlugin.seal(key, aad, clear), second = AxxFilesPlugin.seal(key, aad, clear);
        assertFalse(java.util.Arrays.equals(first, second));
        assertArrayEquals(clear, AxxFilesPlugin.open(key, aad, first));
        try { AxxFilesPlugin.open(key, "wrong-id".getBytes(java.nio.charset.StandardCharsets.UTF_8), first); fail("Wrong identity accepted"); }
        catch (javax.crypto.AEADBadTagException expected) {}
        first[first.length - 1] ^= 1;
        try { AxxFilesPlugin.open(key, aad, first); fail("Tampered ciphertext accepted"); }
        catch (javax.crypto.AEADBadTagException expected) {}
        assertArrayEquals(new byte[0], AxxFilesPlugin.open(key, aad, AxxFilesPlugin.seal(key, aad, new byte[0])));
    }
}
