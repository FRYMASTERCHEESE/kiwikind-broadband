package nz.kiwikind.broadband;

/** Prelaunch policy is independent of debug/release signing. No runtime live-ad switch. */
final class AdPolicy {
    private AdPolicy(){}
    static boolean publicPlacement(String page){return "home".equals(page);}
    static boolean canLoad(boolean consentAllowsAds,boolean recognizedTestDevice,boolean foreground,boolean attached){
        return consentAllowsAds&&recognizedTestDevice&&foreground&&attached;
    }
}
