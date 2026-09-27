#include <windows.h>
#include <rime_api.h>
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

using Clock = std::chrono::steady_clock;

double milliseconds(Clock::time_point start) {
  return std::chrono::duration<double, std::milli>(Clock::now() - start)
      .count();
}

int wmain(int argc, wchar_t** argv) {
  if (argc != 6) {
    std::cerr << "Usage: model-benchmark DLL DATA_DIR SCHEMA CORPUS OUTPUT\n";
    return 2;
  }
  HMODULE library = LoadLibraryExW(
      argv[1], nullptr,
      LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
  if (!library) {
    std::cerr << "Cannot load Rime: " << GetLastError() << '\n';
    return 3;
  }
  auto get_api =
      reinterpret_cast<RimeApi* (*)()>(GetProcAddress(library, "rime_get_api"));
  if (!get_api)
    return 4;
  auto api = get_api();
  if (!RIME_PROVIDED(api, get_version))
    return 4;
  auto root = std::filesystem::absolute(argv[2]);
  auto shared = (root / "shared").u8string();
  auto prebuilt = (root / "shared" / "build").u8string();
  auto user = (root / "user").u8string();
  auto logs = (root / "logs").u8string();
  std::filesystem::create_directories(user);
  std::filesystem::create_directories(logs);
  RIME_STRUCT(RimeTraits, traits);
  traits.shared_data_dir = shared.c_str();
  traits.prebuilt_data_dir = prebuilt.c_str();
  traits.user_data_dir = user.c_str();
  traits.log_dir = logs.c_str();
  traits.app_name = "rime.model_benchmark";
  traits.min_log_level = 2;
  api->setup(&traits);
  api->initialize(nullptr);
  if (!api->find_module("grammar")) {
    std::cerr << "Rime grammar module is unavailable\n";
    api->finalize();
    return 9;
  }
  std::string schema = std::filesystem::path(argv[3]).u8string();
  const auto started = Clock::now();
  auto session = api->create_session();
  if (!session || !api->select_schema(session, schema.c_str())) {
    std::cerr << "Cannot select schema: " << schema << '\n';
    api->finalize();
    return 5;
  }
  const double schema_ms = milliseconds(started);
  api->set_option(session, "ascii_mode", False);
  std::ifstream corpus{std::filesystem::path(argv[4])};
  std::vector<std::pair<std::string, std::string>> cases;
  std::string line;
  while (std::getline(corpus, line)) {
    if (!line.empty() && line.back() == '\r')
      line.pop_back();
    if (line.empty() || line[0] == '#')
      continue;
    auto tab = line.find('\t');
    if (tab == std::string::npos || tab == 0 || tab + 1 == line.size()) {
      std::cerr << "Invalid corpus line\n";
      api->finalize();
      return 6;
    }
    cases.emplace_back(line.substr(0, tab), line.substr(tab + 1));
  }
  if (cases.empty()) {
    std::cerr << "Empty corpus\n";
    api->finalize();
    return 6;
  }
  std::ofstream output{std::filesystem::path(argv[5])};
  if (!output) {
    api->finalize();
    return 7;
  }
  output << "# version=" << api->get_version() << " schema_ms=" << schema_ms
         << '\n';
  output << "round\tpinyin\texpected\ttop1\ttop5_hit\tkey_p50_ms\tkey_p95_ms\n";
  // Warm the dictionary and model before recording three measured rounds.
  for (int round = 0; round < 4; ++round) {
    for (const auto& item : cases) {
      api->clear_composition(session);
      std::vector<double> timings;
      std::vector<std::string> candidates;
      for (unsigned char key : item.first) {
        const auto key_started = Clock::now();
        if (!api->process_key(session, key, 0)) {
          std::cerr << "Unhandled test key\n";
          api->finalize();
          return 8;
        }
        RIME_STRUCT(RimeContext, context);
        candidates.clear();
        if (api->get_context(session, &context)) {
          for (int i = 0; i < context.menu.num_candidates && i < 5; ++i)
            candidates.emplace_back(context.menu.candidates[i].text);
          api->free_context(&context);
        }
        timings.push_back(milliseconds(key_started));
      }
      if (round == 0)
        continue;
      std::sort(timings.begin(), timings.end());
      const auto top1 = candidates.empty() ? std::string() : candidates[0];
      const bool hit = std::find(candidates.begin(), candidates.end(),
                                 item.second) != candidates.end();
      output << round << '\t' << item.first << '\t' << item.second << '\t'
             << top1 << '\t' << hit << '\t' << timings[timings.size() / 2]
             << '\t' << timings[(timings.size() - 1) * 95 / 100] << '\n';
    }
  }
  api->destroy_session(session);
  api->finalize();
  FreeLibrary(library);
  return 0;
}
