#include "stdafx.h"
#include <PipeChannel.h>
#include <boost/detail/lightweight_test.hpp>
#include <cstring>
#include <thread>
#include <vector>

namespace {

using Handle = std::unique_ptr<void, decltype(&::CloseHandle)>;

std::wstring pipe_name() {
  static unsigned int sequence = 0;
  return L"\\\\.\\pipe\\WeaselIPC-test-" +
         std::to_wstring(GetCurrentProcessId()) + L"-" +
         std::to_wstring(++sequence);
}

class TestChannel : public weasel::PipeChannel<DWORD> {
 public:
  explicit TestChannel(std::wstring name)
      : PipeChannel(std::move(name), nullptr, 128) {}

  using PipeChannelBase::_ConnectServerPipe;
  using PipeChannelBase::_Receive;
};

// Each test owns its pipes and never connects to the user's input method.
struct PipePair {
  Handle server{INVALID_HANDLE_VALUE, &::CloseHandle};
  Handle client{INVALID_HANDLE_VALUE, &::CloseHandle};

  PipePair() {
    auto name = pipe_name();
    server.reset(
        CreateNamedPipeW(name.c_str(), PIPE_ACCESS_DUPLEX,
                         PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
                         1, 4096, 4096, 0, nullptr));
    if (server.get() == INVALID_HANDLE_VALUE)
      throw GetLastError();
    client.reset(CreateFileW(name.c_str(), GENERIC_READ | GENERIC_WRITE, 0,
                             nullptr, OPEN_EXISTING, 0, nullptr));
    if (client.get() == INVALID_HANDLE_VALUE)
      throw GetLastError();
    if (!ConnectNamedPipe(server.get(), nullptr) &&
        GetLastError() != ERROR_PIPE_CONNECTED)
      throw GetLastError();
  }

  void Write(const void* data, DWORD size) {
    DWORD written = 0;
    BOOST_TEST(WriteFile(client.get(), data, size, &written, nullptr));
    BOOST_TEST_EQ(size, written);
  }
};

void test_receive() {
  PipePair pipes;
  TestChannel channel(pipe_name());
  DWORD header = 42;
  const std::wstring body = L"action=noop\n.\n";
  std::vector<char> message(sizeof(header) + body.size() * sizeof(wchar_t));
  memcpy(message.data(), &header, sizeof(header));
  memcpy(message.data() + sizeof(header), body.data(),
         body.size() * sizeof(wchar_t));
  pipes.Write(message.data(), static_cast<DWORD>(message.size()));
  DWORD result = 0;
  channel._Receive(pipes.server.get(), &result, sizeof(result));
  BOOST_TEST_EQ(header, result);
  BOOST_TEST(std::wstring(reinterpret_cast<wchar_t*>(channel.ReceiveBuffer()),
                          body.size()) == body);
  std::function<bool(LPWSTR, UINT)> inspect = [&](LPWSTR text, UINT length) {
    BOOST_TEST_EQ(body.size(), length);
    BOOST_TEST(std::wstring(text, length) == body);
    return true;
  };
  BOOST_TEST(channel.HandleResponseData(inspect));

  // A header-only response must not expose the previous response body.
  pipes.Write(&header, sizeof(header));
  channel._Receive(pipes.server.get(), &result, sizeof(result));
  inspect = [](LPWSTR text, UINT length) {
    BOOST_TEST_EQ(0u, length);
    BOOST_TEST_EQ(L'\0', text[0]);
    return true;
  };
  BOOST_TEST(channel.HandleResponseData(inspect));

  // Reject every truncated header length, including an empty message.
  for (DWORD size = 0; size < sizeof(header); ++size) {
    pipes.Write(&header, size);
    bool rejected = false;
    try {
      channel._Receive(pipes.server.get(), &result, sizeof(result));
    } catch (DWORD error) {
      rejected = error == ERROR_INVALID_DATA;
    }
    BOOST_TEST(rejected);
  }

  pipes.client.reset();
  bool disconnected = false;
  try {
    channel._Receive(pipes.server.get(), &result, sizeof(result));
  } catch (DWORD error) {
    disconnected = error == ERROR_BROKEN_PIPE;
  }
  BOOST_TEST(disconnected);
}

void test_oversized_body() {
  PipePair pipes;
  TestChannel channel(pipe_name());
  std::vector<char> message(256, 'x');
  pipes.Write(message.data(), static_cast<DWORD>(message.size()));
  DWORD result = 0;
  bool rejected = false;
  try {
    channel._Receive(pipes.server.get(), &result, sizeof(result));
  } catch (DWORD error) {
    rejected = error == ERROR_MORE_DATA;
  }
  BOOST_TEST(rejected);
}

void test_connections() {
  // Exercise connection setup repeatedly with real Win32 pipes.
  for (int i = 0; i < 16; ++i) {
    auto name = pipe_name();
    TestChannel channel(name);
    DWORD server_error = ERROR_SUCCESS;
    std::thread listener([&] {
      try {
        Handle server(channel._ConnectServerPipe(name), &::CloseHandle);
        DWORD message = 0;
        channel._Receive(server.get(), &message, sizeof(message));
        if (message != 42)
          server_error = ERROR_INVALID_DATA;
      } catch (DWORD error) {
        server_error = error;
      }
    });
    Handle client(INVALID_HANDLE_VALUE, &::CloseHandle);
    const auto deadline = GetTickCount64() + 5000;
    do {
      client.reset(CreateFileW(name.c_str(), GENERIC_READ | GENERIC_WRITE, 0,
                               nullptr, OPEN_EXISTING, 0, nullptr));
      if (client.get() != INVALID_HANDLE_VALUE)
        break;
      Sleep(1);
    } while (GetTickCount64() < deadline);
    const bool connected = client.get() != INVALID_HANDLE_VALUE;
    BOOST_TEST(connected);
    if (connected) {
      DWORD message = 42;
      DWORD written = 0;
      BOOST_TEST(WriteFile(client.get(), &message, sizeof(message), &written,
                           nullptr));
    } else {
      CancelSynchronousIo(listener.native_handle());
    }
    listener.join();
    BOOST_TEST_EQ(ERROR_SUCCESS, server_error);
  }
}

}  // namespace

void test_pipe_channel() {
  test_receive();
  test_oversized_body();
  test_connections();
}
