cmake_minimum_required(VERSION 3.20)

project(CFSS_CPP_CORE
    VERSION 0.1.0
    DESCRIPTION "Crypto Futures Signal System C++ foundation"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(CTest)
find_package(CURL REQUIRED)

add_executable(market_pipeline
    apps/market_pipeline/main.cpp
)
target_link_libraries(market_pipeline PRIVATE CURL::libcurl)
target_compile_features(market_pipeline PRIVATE cxx_std_20)

add_executable(telegram_delivery
    apps/telegram_delivery/main.cpp
)
target_link_libraries(telegram_delivery PRIVATE CURL::libcurl)
target_compile_features(telegram_delivery PRIVATE cxx_std_20)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    foreach(target market_pipeline telegram_delivery)
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
