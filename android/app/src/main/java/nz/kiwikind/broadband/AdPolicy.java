package nz.kiwikind.broadband;

/** Consent and placement remain mandatory; debug builds accept test devices only. */
final class AdPolicy {
    private AdPolicy(){}
    static boolean publicPlacement(String page){return "home".equals(page);}
    static boolean canRequest(boolean liveAdsEnabled,boolean recognizedTestDevice){
        return liveAdsEnabled||recognizedTestDevice;
    }
    static boolean canLoad(boolean consentAllowsAds,boolean recognizedTestDevice,boolean foreground,boolean attached,boolean liveAdsEnabled){
        return consentAllowsAds&&canRequest(liveAdsEnabled,recognizedTestDevice)&&foreground&&attached;
    }
}
