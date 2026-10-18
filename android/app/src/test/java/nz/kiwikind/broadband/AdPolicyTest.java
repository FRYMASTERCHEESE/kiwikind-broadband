package nz.kiwikind.broadband;
import org.junit.Test;
import static org.junit.Assert.*;
public class AdPolicyTest {
    @Test public void onlyPublicHomeHasPlacement(){
        assertTrue(AdPolicy.publicPlacement("home"));
        for(String page:new String[]{null,"login","privacy","deletion","account","billing","support","why","questions"})assertFalse(AdPolicy.publicPlacement(page));
    }
    @Test public void noRequestWithoutEachIndependentGate(){
        for(int bits=0;bits<16;bits++)assertEquals(bits==15,AdPolicy.canLoad((bits&1)!=0,(bits&2)!=0,(bits&4)!=0,(bits&8)!=0));
    }
}
