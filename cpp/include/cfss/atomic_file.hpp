#pragma once
#include <cerrno>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <system_error>
#include <fcntl.h>
#include <unistd.h>

namespace cfss {
inline void write_file_atomic(const std::filesystem::path& path, const std::string& content,
                              bool refuse_existing = false) {
    const auto parent = path.parent_path().empty() ? std::filesystem::path{"."} : path.parent_path();
    std::filesystem::create_directories(parent);
    if (refuse_existing && std::filesystem::exists(path))
        throw std::runtime_error("immutable_artifact_already_exists");

    const auto temp = path.string() + ".tmp." + std::to_string(static_cast<long long>(::getpid()));
    {
        std::ofstream output(temp, std::ios::binary | std::ios::trunc);
        if (!output) throw std::runtime_error("atomic_temp_open_failed");
        output.write(content.data(), static_cast<std::streamsize>(content.size()));
        output.flush();
        if (!output) throw std::runtime_error("atomic_temp_write_failed");
    }

    const int file_fd = ::open(temp.c_str(), O_RDONLY | O_CLOEXEC);
    if (file_fd < 0) throw std::system_error(errno, std::generic_category(), "atomic_temp_open_for_fsync");
    if (::fsync(file_fd) != 0) {
        const int error = errno;
        (void)::close(file_fd);
        throw std::system_error(error, std::generic_category(), "atomic_temp_fsync");
    }
    if (::close(file_fd) != 0)
        throw std::system_error(errno, std::generic_category(), "atomic_temp_close");

    if (refuse_existing && std::filesystem::exists(path))
        throw std::runtime_error("immutable_artifact_already_exists");
    std::filesystem::rename(temp, path);

    const int directory_fd = ::open(parent.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (directory_fd < 0)
        throw std::system_error(errno, std::generic_category(), "atomic_directory_open");
    if (::fsync(directory_fd) != 0) {
        const int error = errno;
        (void)::close(directory_fd);
        throw std::system_error(error, std::generic_category(), "atomic_directory_fsync");
    }
    if (::close(directory_fd) != 0)
        throw std::system_error(errno, std::generic_category(), "atomic_directory_close");
}
} // namespace cfss
