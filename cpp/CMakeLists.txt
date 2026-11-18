cmake_minimum_required(VERSION 3.20)

project(CFSS_CPP_CORE
    VERSION 0.2.0
    DESCRIPTION "Crypto Futures Signal System C++ vertical slice"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

enable_testing()
include(CTest)
find_package(CURL REQUIRED)
find_package(nlohmann_json 3.11 REQUIRED)
find_package(OpenSSL REQUIRED COMPONENTS Crypto)

add_executable(market_pipeline apps/market_pipeline/main.cpp)
target_include_directories(market_pipeline PRIVATE include)
target_link_libraries(market_pipeline PRIVATE CURL::libcurl nlohmann_json::nlohmann_json OpenSSL::Crypto)
target_compile_features(market_pipeline PRIVATE cxx_std_20)

add_executable(telegram_delivery apps/telegram_delivery/main.cpp)
target_include_directories(telegram_delivery PRIVATE include)
target_link_libraries(telegram_delivery PRIVATE CURL::libcurl OpenSSL::Crypto)
target_compile_features(telegram_delivery PRIVATE cxx_std_20)

add_executable(telegram_inbound apps/telegram_inbound/main.cpp)
target_include_directories(telegram_inbound PRIVATE include)
target_link_libraries(telegram_inbound PRIVATE CURL::libcurl OpenSSL::Crypto)
target_compile_features(telegram_inbound PRIVATE cxx_std_20)

add_executable(cfss_unit_tests tests/test_main.cpp)
target_include_directories(cfss_unit_tests PRIVATE include)
target_compile_features(cfss_unit_tests PRIVATE cxx_std_20)
target_link_libraries(cfss_unit_tests PRIVATE nlohmann_json::nlohmann_json CURL::libcurl OpenSSL::Crypto)
add_test(NAME cfss_unit_tests COMMAND cfss_unit_tests)

add_executable(lfs_telegram_report apps/lfs_telegram_report/main.cpp)
target_include_directories(lfs_telegram_report PRIVATE include)
target_compile_features(lfs_telegram_report PRIVATE cxx_std_20)
target_link_libraries(lfs_telegram_report PRIVATE CURL::libcurl nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(lfs_delivery_tests tests/lfs_delivery_test.cpp)
target_include_directories(lfs_delivery_tests PRIVATE include)
target_compile_features(lfs_delivery_tests PRIVATE cxx_std_20)
target_link_libraries(lfs_delivery_tests PRIVATE OpenSSL::Crypto nlohmann_json::nlohmann_json)
add_test(NAME lfs_delivery_tests COMMAND lfs_delivery_tests)

add_executable(lfs_v2_probe apps/lfs_v2_probe/main.cpp)
target_include_directories(lfs_v2_probe PRIVATE include)
target_compile_features(lfs_v2_probe PRIVATE cxx_std_20)
target_link_libraries(lfs_v2_probe PRIVATE CURL::libcurl nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(lfs_v2_tests tests/lfs_v2_test.cpp)
target_include_directories(lfs_v2_tests PRIVATE include)
target_compile_features(lfs_v2_tests PRIVATE cxx_std_20)
add_test(NAME lfs_v2_tests COMMAND lfs_v2_tests)

add_executable(lfs_v1_probe apps/lfs_v1_probe/main.cpp)
target_compile_features(lfs_v1_probe PRIVATE cxx_std_20)
target_link_libraries(lfs_v1_probe PRIVATE nlohmann_json::nlohmann_json)

add_executable(lfs_v1_tests tests/lfs_v1_test.cpp)
target_include_directories(lfs_v1_tests PRIVATE include)
target_compile_features(lfs_v1_tests PRIVATE cxx_std_20)
add_test(NAME lfs_v1_tests COMMAND lfs_v1_tests)

add_executable(nss_v1_probe apps/nss_v1_probe/main.cpp)
target_include_directories(nss_v1_probe PRIVATE include)
target_compile_features(nss_v1_probe PRIVATE cxx_std_20)
target_link_libraries(nss_v1_probe PRIVATE nlohmann_json::nlohmann_json)

add_executable(nss_telegram_report apps/nss_telegram_report/main.cpp)
target_include_directories(nss_telegram_report PRIVATE include)
target_compile_features(nss_telegram_report PRIVATE cxx_std_20)
target_link_libraries(nss_telegram_report PRIVATE CURL::libcurl nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(nss_basis_collector apps/nss_basis_collector/main.cpp)
target_include_directories(nss_basis_collector PRIVATE include)
target_compile_features(nss_basis_collector PRIVATE cxx_std_20)
target_link_libraries(nss_basis_collector PRIVATE CURL::libcurl nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(nss_v2_probe apps/nss_v2_probe/main.cpp)
target_include_directories(nss_v2_probe PRIVATE include)
target_compile_features(nss_v2_probe PRIVATE cxx_std_20)
target_link_libraries(nss_v2_probe PRIVATE nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(nss_basis_tests tests/nss_basis_test.cpp)
target_include_directories(nss_basis_tests PRIVATE include)
target_compile_features(nss_basis_tests PRIVATE cxx_std_20)
add_test(NAME nss_basis_tests COMMAND nss_basis_tests)

add_executable(nss_v2_tests tests/nss_v2_test.cpp)
target_include_directories(nss_v2_tests PRIVATE include)
target_compile_features(nss_v2_tests PRIVATE cxx_std_20)
add_test(NAME nss_v2_tests COMMAND nss_v2_tests)

add_executable(liquidity_phase_probe apps/liquidity_phase_probe/main.cpp)
target_include_directories(liquidity_phase_probe PRIVATE include)
target_compile_features(liquidity_phase_probe PRIVATE cxx_std_20)
target_link_libraries(liquidity_phase_probe PRIVATE nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(dual_engine_probe apps/dual_engine_probe/main.cpp)
target_include_directories(dual_engine_probe PRIVATE include)
target_compile_features(dual_engine_probe PRIVATE cxx_std_20)
target_link_libraries(dual_engine_probe PRIVATE nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(meta_calibration_v1_tests tests/meta_calibration_v1_test.cpp)
target_include_directories(meta_calibration_v1_tests PRIVATE include)
target_compile_features(meta_calibration_v1_tests PRIVATE cxx_std_20)
add_test(NAME meta_calibration_v1_tests COMMAND meta_calibration_v1_tests)

add_executable(meta_cognition_probe apps/meta_cognition_probe/main.cpp)
target_include_directories(meta_cognition_probe PRIVATE include)
target_compile_features(meta_cognition_probe PRIVATE cxx_std_20)
target_link_libraries(meta_cognition_probe PRIVATE nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(meta_cognition_telegram_report apps/meta_cognition_telegram_report/main.cpp)
target_include_directories(meta_cognition_telegram_report PRIVATE include)
target_compile_features(meta_cognition_telegram_report PRIVATE cxx_std_20)
target_link_libraries(meta_cognition_telegram_report PRIVATE CURL::libcurl nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(dual_engine_v1_tests tests/dual_engine_v1_test.cpp)
target_include_directories(dual_engine_v1_tests PRIVATE include)
target_compile_features(dual_engine_v1_tests PRIVATE cxx_std_20)
add_test(NAME dual_engine_v1_tests COMMAND dual_engine_v1_tests)

add_executable(dual_engine_telegram_report apps/dual_engine_telegram_report/main.cpp)
target_include_directories(dual_engine_telegram_report PRIVATE include)
target_compile_features(dual_engine_telegram_report PRIVATE cxx_std_20)
target_link_libraries(dual_engine_telegram_report PRIVATE CURL::libcurl nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(liquidity_phase_v1_tests tests/liquidity_phase_v1_test.cpp)
target_include_directories(liquidity_phase_v1_tests PRIVATE include)
target_compile_features(liquidity_phase_v1_tests PRIVATE cxx_std_20)
add_test(NAME liquidity_phase_v1_tests COMMAND liquidity_phase_v1_tests)

add_executable(liquidity_telegram_report apps/liquidity_telegram_report/main.cpp)
target_include_directories(liquidity_telegram_report PRIVATE include)
target_compile_features(liquidity_telegram_report PRIVATE cxx_std_20)
target_link_libraries(liquidity_telegram_report PRIVATE CURL::libcurl nlohmann_json::nlohmann_json OpenSSL::Crypto)

add_executable(nss_v1_tests tests/nss_v1_test.cpp)
target_include_directories(nss_v1_tests PRIVATE include)
target_compile_features(nss_v1_tests PRIVATE cxx_std_20)
add_test(NAME nss_v1_tests COMMAND nss_v1_tests)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    foreach(target market_pipeline telegram_delivery telegram_inbound cfss_unit_tests lfs_telegram_report lfs_delivery_tests lfs_v2_probe lfs_v2_tests lfs_v1_probe lfs_v1_tests nss_v1_probe nss_v1_tests nss_basis_collector nss_v2_probe nss_basis_tests nss_v2_tests nss_telegram_report liquidity_phase_probe liquidity_phase_v1_tests liquidity_telegram_report dual_engine_probe dual_engine_v1_tests meta_calibration_v1_tests meta_cognition_probe meta_cognition_telegram_report)
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion)
    endforeach()
endif()

message(STATUS "CFSS C++ standard: C++${CMAKE_CXX_STANDARD}")
message(STATUS "CFSS libcurl version: ${CURL_VERSION_STRING}")
