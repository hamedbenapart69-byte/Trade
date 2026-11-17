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

add_executable(market_pipeline
    apps/market_pipeline/main.cpp
)
target_include_directories(market_pipeline PRIVATE include)
target_link_libraries(market_pipeline PRIVATE nlohmann_json::nlohmann_json)
target_compile_features(market_pipeline PRIVATE cxx_std_20)

add_executable(telegram_delivery
    apps/telegram_delivery/main.cpp
)
target_include_directories(telegram_delivery PRIVATE include)
target_link_libraries(telegram_delivery PRIVATE CURL::libcurl)
target_compile_features(telegram_delivery PRIVATE cxx_std_20)

add_executable(telegram_inbound
    apps/telegram_inbound/main.cpp
)
target_include_directories(telegram_inbound PRIVATE include)
target_link_libraries(telegram_inbound PRIVATE CURL::libcurl)
target_compile_features(telegram_inbound PRIVATE cxx_std_20)

add_executable(cfss_unit_tests tests/test_main.cpp)
target_include_directories(cfss_unit_tests PRIVATE include)
target_compile_features(cfss_unit_tests PRIVATE cxx_std_20)
target_link_libraries(cfss_unit_tests PRIVATE nlohmann_json::nlohmann_json CURL::libcurl)
add_test(NAME cfss_unit_tests COMMAND cfss_unit_tests)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    foreach(target market_pipeline telegram_delivery telegram_inbound cfss_unit_tests)
        target_compile_options(${target} PRIVATE
            -Wall
            -Wextra
            -Wpedantic
            -Wconversion
            -Wsign-conversion
        )
    endforeach()
endif()

message(STATUS "CFSS C++ standard: C++${CMAKE_CXX_STANDARD}")
message(STATUS "CFSS libcurl version: ${CURL_VERSION_STRING}")
