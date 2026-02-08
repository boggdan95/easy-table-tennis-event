-- ETTEM License Server - Database Schema
-- Run this in cPanel > phpMyAdmin to create the tables

CREATE TABLE IF NOT EXISTS licenses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    license_key VARCHAR(30) NOT NULL UNIQUE,
    client_id VARCHAR(4) NOT NULL,
    client_name VARCHAR(100) DEFAULT NULL,
    client_email VARCHAR(200) DEFAULT NULL,
    expiration_date DATE NOT NULL,
    max_machines INT NOT NULL DEFAULT 2,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    notes TEXT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_client_id (client_id),
    INDEX idx_license_key (license_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS machines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    license_id INT NOT NULL,
    machine_id VARCHAR(64) NOT NULL,
    machine_label VARCHAR(200) DEFAULT NULL,
    first_activated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_validated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    UNIQUE KEY uk_license_machine (license_id, machine_id),
    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE,
    INDEX idx_machine_id (machine_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS validation_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    license_id INT NOT NULL,
    machine_id VARCHAR(64) NOT NULL,
    action ENUM('activate', 'validate', 'deactivate', 'rejected') NOT NULL,
    result ENUM('success', 'expired', 'revoked', 'machine_limit', 'invalid_key', 'error') NOT NULL,
    ip_address VARCHAR(45) DEFAULT NULL,
    app_version VARCHAR(20) DEFAULT NULL,
    details TEXT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE,
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
