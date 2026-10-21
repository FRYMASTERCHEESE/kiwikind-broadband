package nz.kiwikind.broadband;
import org.junit.Test;
import static org.junit.Assert.*;
public class AdPolicyTest {
    @Test public void onlyPublicHomeHasPlacement(){
        assertTrue(AdPolicy.publicPlacement("home"));
        for(String page:new String[]{null,"login","privacy","deletion","account","billing","support","why","questions"})assertFalse(AdPolicy.publicPlacement(page));
    }
    @Test public void noRequestWithoutEachIndependentGate(){
        for(int bits=0;bits<32;bits++){
            boolean consent=(bits&1)!=0,testDevice=(bits&2)!=0,foreground=(bits&4)!=0,attached=(bits&8)!=0,live=(bits&16)!=0;
            assertEquals(consent&&foreground&&attached&&(testDevice||live),AdPolicy.canLoad(consent,testDevice,foreground,attached,live));
        }
    }
}
