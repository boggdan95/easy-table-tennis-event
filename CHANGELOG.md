# Changelog

All notable changes to Easy Table Tennis Event Manager (ettem) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- ITTF-compliant BYE positioning in manual bracket based on number of groups
  - Predefined BYE positions for 3-20 groups
  - Example: 3 groups → positions [2, 7], 5 groups → positions [2, 6, 7, 10, 11, 15]
- Drag-and-drop support within bracket (move/swap players between slots)
- Removable and repositionable BYEs
  - Click X button to remove BYE from slot
  - Removed BYEs appear in "BYEs Disponibles" pool
  - Drag BYEs from pool to empty slots
- Player swap functionality (drag occupied slot to another occupied slot)
- Enhanced drag validation for BYE vs player interactions

### Changed
- Simplified BYE display text (removed ITTF subtitle)
- Updated manual bracket instructions to explain BYE management

### Technical
- Added `get_bye_positions()` function in `app.py` for ITTF BYE positioning
- Enhanced `handleDrop()` JavaScript function to support slot-to-slot dragging
- Added `assignByeToSlot()` and `addByeToPool()` JavaScript functions

## [1.0.1] - 2025-01-XX

### Added
- Edit/delete match results functionality
- Score validation module with table tennis rules
- Comprehensive test suite for validation
- Bracket visualization

### Fixed
- Compute-standings CLI to use nombre/apellido instead of full_name

## [1.0.0] - 2025-01-XX

### Added
- Initial release with V1 features
- Player registration from CSV
- Round Robin group generation with snake seeding
- Automatic fixture generation using circle method
- Local web panel for manual result entry
- Standings calculation with advanced tie-breaking
- Knockout bracket generation
- SQLite persistence
- Internationalization (Spanish/English)
- CSV export for groups, standings, and brackets

[Unreleased]: https://github.com/yourusername/ettem/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/yourusername/ettem/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/yourusername/ettem/releases/tag/v1.0.0
