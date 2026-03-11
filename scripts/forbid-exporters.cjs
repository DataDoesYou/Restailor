#!/usr/bin/env node
/**
 * CI Guard: Forbid Exporter Patterns
 * 
 * Scans the repository for forbidden export patterns that could leak analytics
 * data to the browser or via CSV downloads. This ensures the analytics layer
 * remains the single source of truth.
 * 
 * Exit codes:
 *   0 - No violations found
 *   1 - Violations found (fails CI)
 * 
 * Usage:
 *   node scripts/forbid-exporters.cjs
 *   npm run ci:forbid-exporters
 */

const fs = require('fs');
const path = require('path');

// Forbidden patterns that indicate export functionality
const FORBIDDEN_PATTERNS = [
  {
    pattern: /window\.__export/gi,
    name: 'window.__export*',
    description: 'Browser window export helpers',
  },
  {
    pattern: /exportCsv/gi,
    name: 'exportCsv',
    description: 'CSV export functions',
  },
  {
    pattern: /toCSV\(/gi,
    name: 'toCSV(',
    description: 'toCSV function calls',
  },
  {
    pattern: /csv-stringify/gi,
    name: 'csv-stringify',
    description: 'csv-stringify library usage',
  },
  {
    pattern: /getAnalyticsExportUrl/gi,
    name: 'getAnalyticsExportUrl',
    description: 'Analytics export URL generator',
  },
  {
    pattern: /\/analytics\/export\.csv/gi,
    name: '/analytics/export.csv',
    description: 'Analytics CSV export endpoint',
  },
  {
    pattern: /text\/csv/gi,
    name: 'text/csv',
    description: 'CSV content type header',
  },
];

// Directories to ignore
const IGNORED_DIRS = [
  'node_modules',
  '.next',
  '.output',
  'dist',
  'build',
  '__pycache__',
  '.git',
  '.pytest_cache',
  'htmlcov',
  '.venv',
  'venv',
  '.mypy_cache',
  '.ruff_cache',
];

// Files to ignore (allowed exceptions)
const IGNORED_FILES = [
  'forbid-exporters.cjs', // This file
  'no-exporters-in-prod.test.ts', // Test file that checks for these patterns
  'test_csv_export_removed.py', // Backend test that verifies removal
  'test_analytics_endpoints.py', // Test that verifies endpoint returns 404
  'test_analytics_summary.py', // Test that verifies endpoint returns 404
  'FRONTEND_EXPORTER_REMOVAL.md', // Documentation
  'BACKEND_CSV_EXPORT_REMOVAL.md', // Documentation
  'pull_request_template.md', // PR template
  'PROJECT-OVERVIEW.md', // Documentation with examples
  'QUICK-REFERENCE.md', // Documentation with examples
  'stageAnalyticsHelpers.ts', // Dev-only helpers (gated with NODE_ENV)
  'assertNoExports.ts', // Security guard (references patterns it checks for)
  'analytics.py', // Comment explaining removal (not actual endpoint)
];

// Extensions to scan
const SCANNED_EXTENSIONS = [
  '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
  '.py', '.md', '.yml', '.yaml',
];

let violations = [];

/**
 * Check if a path should be ignored
 */
function shouldIgnore(filePath) {
  const parts = filePath.split(path.sep);
  
  // Check ignored directories
  for (const dir of IGNORED_DIRS) {
    if (parts.includes(dir)) {
      return true;
    }
  }
  
  // Check ignored files
  const fileName = path.basename(filePath);
  if (IGNORED_FILES.includes(fileName)) {
    return true;
  }
  
  return false;
}

/**
 * Check if file extension should be scanned
 */
function shouldScanFile(filePath) {
  const ext = path.extname(filePath);
  return SCANNED_EXTENSIONS.includes(ext);
}

/**
 * Scan a file for forbidden patterns
 */
function scanFile(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');
    
    for (const { pattern, name, description } of FORBIDDEN_PATTERNS) {
      lines.forEach((line, lineNumber) => {
        if (pattern.test(line)) {
          violations.push({
            file: filePath,
            line: lineNumber + 1,
            pattern: name,
            description,
            content: line.trim(),
          });
        }
      });
    }
  } catch (error) {
    // Skip files that can't be read (binary, permission issues, etc.)
    if (error.code !== 'EISDIR') {
      console.warn(`⚠️  Warning: Could not read ${filePath}: ${error.message}`);
    }
  }
}

/**
 * Recursively scan directory
 */
function scanDirectory(dirPath) {
  if (shouldIgnore(dirPath)) {
    return;
  }
  
  try {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    
    for (const entry of entries) {
      const fullPath = path.join(dirPath, entry.name);
      
      if (shouldIgnore(fullPath)) {
        continue;
      }
      
      if (entry.isDirectory()) {
        scanDirectory(fullPath);
      } else if (entry.isFile() && shouldScanFile(fullPath)) {
        scanFile(fullPath);
      }
    }
  } catch (error) {
    console.warn(`⚠️  Warning: Could not scan directory ${dirPath}: ${error.message}`);
  }
}

/**
 * Main execution
 */
function main() {
  console.log('🔍 Scanning repository for forbidden exporter patterns...\n');
  
  const rootDir = path.resolve(__dirname, '..');
  scanDirectory(rootDir);
  
  if (violations.length === 0) {
    console.log('✅ No forbidden export patterns found!\n');
    process.exit(0);
  }
  
  // Group violations by file
  const violationsByFile = {};
  for (const violation of violations) {
    if (!violationsByFile[violation.file]) {
      violationsByFile[violation.file] = [];
    }
    violationsByFile[violation.file].push(violation);
  }
  
  // Print violations
  console.error('❌ Found forbidden export patterns:\n');
  
  for (const [file, fileViolations] of Object.entries(violationsByFile)) {
    const relPath = path.relative(rootDir, file);
    console.error(`📄 ${relPath}`);
    
    for (const v of fileViolations) {
      console.error(`   Line ${v.line}: ${v.pattern} - ${v.description}`);
      console.error(`   > ${v.content}`);
    }
    console.error('');
  }
  
  console.error(`\n💥 Total: ${violations.length} violation(s) in ${Object.keys(violationsByFile).length} file(s)\n`);
  console.error('These patterns are forbidden to prevent data leakage via exports.');
  console.error('Analytics data must be accessed via the analytics schema only.\n');
  console.error('See docs/FRONTEND_EXPORTER_REMOVAL.md and docs/BACKEND_CSV_EXPORT_REMOVAL.md\n');
  
  process.exit(1);
}

// Run if called directly
if (require.main === module) {
  main();
}

module.exports = { scanFile, scanDirectory, FORBIDDEN_PATTERNS };
