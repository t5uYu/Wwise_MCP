#pragma once

#include <AK/Wwise/Plugin.h>

/// WwiseBridge Authoring Plugin
///
/// The actual WebSocket server (BridgeServer) lives in a static global
/// (see WwiseBridgePlugin.cpp) and starts the moment Wwise loads the DLL.
/// This class is only the thin Authoring-side shell required by the SDK.
class WwiseBridgePlugin final
    : public AK::Wwise::Plugin::AudioPlugin
{
public:
    WwiseBridgePlugin();
    ~WwiseBridgePlugin() override;

    /// No audio parameters to serialise — WwiseBridge is a pure tool plugin.
    bool GetBankParameters(const GUID& in_guidPlatform,
                           AK::Wwise::Plugin::DataWriter& in_dataWriter) const override
    {
        return true;
    }
};

AK_DECLARE_PLUGIN_CONTAINER(WwiseBridge);
