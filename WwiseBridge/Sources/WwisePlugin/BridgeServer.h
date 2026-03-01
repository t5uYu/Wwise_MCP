#pragma once

#include <string>
#include <thread>
#include <atomic>
#include <mutex>

// Forward declaration — full Winsock types live in stdafx.h
typedef unsigned long long SOCKET_TYPE;

/// Minimal WebSocket server (Winsock2, no third-party libs)
/// Phase 1: accepts one client at a time, handles ping → pong.
class BridgeServer
{
public:
    BridgeServer();
    ~BridgeServer();

    /// Start listening on the given port (non-blocking — spins up a thread).
    void Start(int port = 8081);

    /// Stop the server and join the background thread.
    void Stop();

    bool IsRunning() const { return m_running.load(); }

private:
    void ServerLoop(int port);
    void HandleClient(uintptr_t clientSocket);

    /// Performs the HTTP→WebSocket upgrade handshake.
    /// Returns true on success.
    bool Handshake(uintptr_t clientSocket);

    /// Reads one WebSocket frame payload and returns the decoded text.
    /// Returns empty string on error / connection close.
    std::string ReadFrame(uintptr_t clientSocket);

    /// Sends a text WebSocket frame.
    bool SendFrame(uintptr_t clientSocket, const std::string& text);

    /// Builds the ping response JSON from the incoming JSON.
    std::string BuildPongResponse(const std::string& requestJson);

    // ---- helpers ----
    static std::string Base64Encode(const unsigned char* data, size_t len);
    static std::string Sha1Base64(const std::string& input);

    std::thread       m_thread;
    std::atomic<bool> m_running{ false };
    uintptr_t         m_listenSocket{ 0 }; // INVALID_SOCKET == ~0ull on x64
    std::mutex        m_stopMutex;
};
