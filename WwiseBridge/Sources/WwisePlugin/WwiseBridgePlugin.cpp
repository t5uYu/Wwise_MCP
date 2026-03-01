#include "stdafx.h"
#include "WwiseBridgePlugin.h"
#include "BridgeServer.h"

// ---------------------------------------------------------------------------
// Module-level server: starts when the DLL is loaded by Wwise Authoring,
// stops when the DLL is unloaded (Wwise exits).
//
// Using a static global rather than starting in WwiseBridgePlugin::ctor
// because Wwise only creates a plugin INSTANCE when a user drags the plugin
// into a project — the DLL load itself does NOT trigger a ctor call.
// ---------------------------------------------------------------------------
namespace {
    struct AutoServer
    {
        BridgeServer server;
        AutoServer()  { server.Start(8081); }
        ~AutoServer() { server.Stop(); }
    };
    // Constructed at DLL-attach time (static initialiser order is well-defined
    // within a translation unit; Winsock WSAStartup is called in BridgeServer.cpp
    // via its own static guard before this runs).
    static AutoServer g_autoServer;
}

// ---------------------------------------------------------------------------
// WwiseBridgePlugin — thin authoring-side class (no per-instance server)
// ---------------------------------------------------------------------------

WwiseBridgePlugin::WwiseBridgePlugin()  = default;
WwiseBridgePlugin::~WwiseBridgePlugin() = default;

// ---------------------------------------------------------------------------
// Plugin container registration
//
// AK_ADD_PLUGIN_CLASSID_TO_CONTAINER is used instead of the usual
// AK_ADD_PLUGIN_CLASS_TO_CONTAINER because WwiseBridge is Authoring-only —
// it has no matching SoundEngine FX library.
//
// CompanyID 64     = Audiokinetic custom plug-in company slot
// PluginID  0xBB01 = unique ID for WwiseBridge (change if it conflicts)
// ---------------------------------------------------------------------------

AK_DEFINE_PLUGIN_CONTAINER(WwiseBridge);
AK_EXPORT_PLUGIN_CONTAINER(WwiseBridge);
AK_ADD_PLUGIN_CLASSID_TO_CONTAINER(
    WwiseBridge,
    WwiseBridgePlugin,
    64,
    0xBB01,
    AkPluginTypeEffect
);

DEFINE_PLUGIN_REGISTER_HOOK
DEFINEDUMMYASSERTHOOK;
