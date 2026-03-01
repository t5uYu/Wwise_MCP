#include "stdafx.h"
#include "BridgeServer.h"

#pragma comment(lib, "Ws2_32.lib")
#pragma comment(lib, "Bcrypt.lib")

// ---------------------------------------------------------------------------
// Winsock RAII guard so we never forget WSACleanup
// ---------------------------------------------------------------------------
namespace {
    struct WsaGuard {
        WsaGuard()  { WSADATA d; WSAStartup(MAKEWORD(2,2), &d); }
        ~WsaGuard() { WSACleanup(); }
    };
    WsaGuard g_wsaGuard;

    // WebSocket magic GUID (RFC 6455)
    static const char* WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    // Wwise version string embedded in responses
    static const char* WWISE_VERSION = "2024.1.8";
}

// ---------------------------------------------------------------------------
// SHA-1 via Windows BCrypt (no OpenSSL required)
// ---------------------------------------------------------------------------
std::string BridgeServer::Sha1Base64(const std::string& input)
{
    BCRYPT_ALG_HANDLE hAlg = nullptr;
    BCRYPT_HASH_HANDLE hHash = nullptr;
    NTSTATUS status;

    status = BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_SHA1_ALGORITHM, nullptr, 0);
    if (!BCRYPT_SUCCESS(status)) return {};

    DWORD hashObjSize = 0, dataLen = 0;
    BCryptGetProperty(hAlg, BCRYPT_OBJECT_LENGTH, (PUCHAR)&hashObjSize, sizeof(DWORD), &dataLen, 0);

    std::vector<BYTE> hashObj(hashObjSize);
    status = BCryptCreateHash(hAlg, &hHash, hashObj.data(), hashObjSize, nullptr, 0, 0);
    if (!BCRYPT_SUCCESS(status)) { BCryptCloseAlgorithmProvider(hAlg, 0); return {}; }

    BCryptHashData(hHash, (PUCHAR)input.data(), (ULONG)input.size(), 0);

    unsigned char digest[20];
    BCryptFinishHash(hHash, digest, sizeof(digest), 0);
    BCryptDestroyHash(hHash);
    BCryptCloseAlgorithmProvider(hAlg, 0);

    return Base64Encode(digest, sizeof(digest));
}

// ---------------------------------------------------------------------------
// Base64 encoder
// ---------------------------------------------------------------------------
std::string BridgeServer::Base64Encode(const unsigned char* data, size_t len)
{
    static const char* tbl = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    out.reserve(((len + 2) / 3) * 4);
    for (size_t i = 0; i < len; i += 3)
    {
        unsigned int v = (unsigned char)data[i] << 16;
        if (i+1 < len) v |= (unsigned char)data[i+1] << 8;
        if (i+2 < len) v |= (unsigned char)data[i+2];
        out += tbl[(v >> 18) & 0x3F];
        out += tbl[(v >> 12) & 0x3F];
        out += (i+1 < len) ? tbl[(v >>  6) & 0x3F] : '=';
        out += (i+2 < len) ? tbl[(v      ) & 0x3F] : '=';
    }
    return out;
}

// ---------------------------------------------------------------------------
// BridgeServer
// ---------------------------------------------------------------------------
BridgeServer::BridgeServer()  = default;
BridgeServer::~BridgeServer() { Stop(); }

void BridgeServer::Start(int port)
{
    if (m_running.load()) return;
    m_running = true;
    m_thread = std::thread(&BridgeServer::ServerLoop, this, port);
}

void BridgeServer::Stop()
{
    m_running = false;
    // Wake up the blocking accept() by closing the listen socket
    if (m_listenSocket != 0 && m_listenSocket != (uintptr_t)(~0ull))
    {
        closesocket((SOCKET)m_listenSocket);
        m_listenSocket = (uintptr_t)(~0ull); // INVALID_SOCKET
    }
    if (m_thread.joinable())
        m_thread.join();
}

// ---------------------------------------------------------------------------
// Main server loop
// ---------------------------------------------------------------------------
void BridgeServer::ServerLoop(int port)
{
    SOCKET listenSock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (listenSock == INVALID_SOCKET) { m_running = false; return; }
    m_listenSocket = (uintptr_t)listenSock;

    // Allow quick restart after Wwise reload
    BOOL reuse = TRUE;
    setsockopt(listenSock, SOL_SOCKET, SO_REUSEADDR, (char*)&reuse, sizeof(reuse));

    sockaddr_in addr{};
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK); // 127.0.0.1 only
    addr.sin_port        = htons((u_short)port);

    if (bind(listenSock, (sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR ||
        listen(listenSock, SOMAXCONN) == SOCKET_ERROR)
    {
        closesocket(listenSock);
        m_running = false;
        return;
    }

    while (m_running.load())
    {
        SOCKET client = accept(listenSock, nullptr, nullptr);
        if (client == INVALID_SOCKET) break; // stop was called or error
        HandleClient((uintptr_t)client);
    }

    closesocket(listenSock);
    m_listenSocket = (uintptr_t)(~0ull);
    m_running = false;
}

// ---------------------------------------------------------------------------
// Per-client handler
// ---------------------------------------------------------------------------
void BridgeServer::HandleClient(uintptr_t clientSocket)
{
    SOCKET sock = (SOCKET)clientSocket;

    if (!Handshake(sock))
    {
        closesocket(sock);
        return;
    }

    while (m_running.load())
    {
        std::string msg = ReadFrame(sock);
        if (msg.empty()) break;

        std::string response = BuildPongResponse(msg);
        if (response.empty()) continue; // unrecognised action — skip

        if (!SendFrame(sock, response)) break;
    }

    closesocket(sock);
}

// ---------------------------------------------------------------------------
// WebSocket handshake (RFC 6455)
// ---------------------------------------------------------------------------
bool BridgeServer::Handshake(uintptr_t clientSocket)
{
    SOCKET sock = (SOCKET)clientSocket;
    char buf[4096] = {};
    int received = recv(sock, buf, sizeof(buf)-1, 0);
    if (received <= 0) return false;

    std::string request(buf, received);

    // Extract Sec-WebSocket-Key
    const char* keyHeader = "Sec-WebSocket-Key: ";
    auto pos = request.find(keyHeader);
    if (pos == std::string::npos) return false;
    pos += strlen(keyHeader);
    auto end = request.find("\r\n", pos);
    if (end == std::string::npos) return false;
    std::string wsKey = request.substr(pos, end - pos);

    // Compute accept key: SHA1(key + GUID), then base64
    std::string acceptKey = Sha1Base64(wsKey + WS_GUID);

    std::string response =
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Accept: " + acceptKey + "\r\n"
        "\r\n";

    return send(sock, response.c_str(), (int)response.size(), 0) == (int)response.size();
}

// ---------------------------------------------------------------------------
// Read a single WebSocket text frame (opcode 0x1), unmasked payload returned.
// Supports only frames whose payload fits in 64 KB (sufficient for Phase 1).
// ---------------------------------------------------------------------------
std::string BridgeServer::ReadFrame(uintptr_t clientSocket)
{
    SOCKET sock = (SOCKET)clientSocket;
    unsigned char header[2];
    if (recv(sock, (char*)header, 2, MSG_WAITALL) != 2) return {};

    // bool fin  = (header[0] & 0x80) != 0;
    int  opcode = header[0] & 0x0F;
    bool masked = (header[1] & 0x80) != 0;
    uint64_t payloadLen = header[1] & 0x7F;

    // Handle extended payload length
    if (payloadLen == 126)
    {
        unsigned char ext[2];
        if (recv(sock, (char*)ext, 2, MSG_WAITALL) != 2) return {};
        payloadLen = ((uint64_t)ext[0] << 8) | ext[1];
    }
    else if (payloadLen == 127)
    {
        unsigned char ext[8];
        if (recv(sock, (char*)ext, 8, MSG_WAITALL) != 8) return {};
        payloadLen = 0;
        for (int i = 0; i < 8; ++i) payloadLen = (payloadLen << 8) | ext[i];
    }

    // Masking key (clients must always mask)
    unsigned char maskKey[4] = {};
    if (masked)
    {
        if (recv(sock, (char*)maskKey, 4, MSG_WAITALL) != 4) return {};
    }

    // Connection close frame
    if (opcode == 0x8) return {};

    // We only handle text frames (0x1) and continuation (0x0)
    if (opcode != 0x1 && opcode != 0x0) return {};

    if (payloadLen == 0) return {};
    if (payloadLen > 65536) return {}; // Guard against large payloads in Phase 1

    std::vector<char> payload((size_t)payloadLen);
    int got = recv(sock, payload.data(), (int)payloadLen, MSG_WAITALL);
    if (got != (int)payloadLen) return {};

    if (masked)
    {
        for (int i = 0; i < got; ++i)
            payload[i] ^= maskKey[i % 4];
    }

    return std::string(payload.begin(), payload.end());
}

// ---------------------------------------------------------------------------
// Send a WebSocket text frame (server→client, unmasked per RFC 6455)
// ---------------------------------------------------------------------------
bool BridgeServer::SendFrame(uintptr_t clientSocket, const std::string& text)
{
    SOCKET sock = (SOCKET)clientSocket;
    size_t len = text.size();

    std::vector<unsigned char> frame;
    frame.push_back(0x81); // FIN + text opcode

    if (len <= 125)
    {
        frame.push_back((unsigned char)len);
    }
    else if (len <= 65535)
    {
        frame.push_back(126);
        frame.push_back((unsigned char)(len >> 8));
        frame.push_back((unsigned char)(len & 0xFF));
    }
    else
    {
        frame.push_back(127);
        for (int i = 7; i >= 0; --i)
            frame.push_back((unsigned char)((len >> (8*i)) & 0xFF));
    }

    frame.insert(frame.end(), text.begin(), text.end());
    int sent = send(sock, (char*)frame.data(), (int)frame.size(), 0);
    return sent == (int)frame.size();
}

// ---------------------------------------------------------------------------
// JSON helpers — minimal, no third-party library
// ---------------------------------------------------------------------------
namespace {

    // Extract the string value of a JSON key (simple single-pass scan)
    std::string JsonGetString(const std::string& json, const std::string& key)
    {
        std::string needle = "\"" + key + "\"";
        auto pos = json.find(needle);
        if (pos == std::string::npos) return {};
        pos += needle.size();
        // skip whitespace and colon
        while (pos < json.size() && (json[pos] == ' ' || json[pos] == ':' || json[pos] == '\t')) ++pos;
        if (pos >= json.size() || json[pos] != '"') return {};
        ++pos; // skip opening quote
        auto end = json.find('"', pos);
        if (end == std::string::npos) return {};
        return json.substr(pos, end - pos);
    }

} // anonymous namespace

// ---------------------------------------------------------------------------
// Build pong response JSON
// ---------------------------------------------------------------------------
std::string BridgeServer::BuildPongResponse(const std::string& requestJson)
{
    std::string action = JsonGetString(requestJson, "action");
    if (action != "ping") return {};

    std::string id = JsonGetString(requestJson, "id");
    if (id.empty()) id = "0";

    // {"id":"<id>","success":true,"data":{"message":"pong","wwise_version":"2024.1.8"}}
    std::string resp = "{\"id\":\"" + id + "\","
                       "\"success\":true,"
                       "\"data\":{"
                           "\"message\":\"pong\","
                           "\"wwise_version\":\"" + std::string(WWISE_VERSION) + "\""
                       "}}";
    return resp;
}
