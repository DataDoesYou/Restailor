#!/usr/bin/env node
/**
 * Build-Time Bundle Verification: Forbid Exporter Patterns in Production Build
 * 
 * This script scans the compiled Next.js production bundle (.next directory)
 * for forbidden export patterns as a final safety check. It runs automatically
 * after 'npm run build:prod' via the postbuild:prod hook.
 * 
 * Why this check is needed:
 * 1. Tree-shaking failures could leak gated code
 * 2. Minification/bundling might preserve export patterns
 * 3. Third-party dependencies could introduce exporters
 * 4. Acts as defense-in-depth (catches what source code scanner misses)
 * 
 * Exit codes:
 *   0 - No violations found in production bundle
 *   1 - Violations found (fails build)
 * 
 * Usage:
 *   node scripts/verify-prod-bundle.cjs
 *   npm run postbuild:prod (automatic after build:prod)
 */

const fs = require('fs');
const path = require('path');

// Same forbidden patterns as CI source code scanner
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

// Build output directory to scan
const BUILD_DIR = path.join(__dirname, '..', 'frontend', '.next');

// File extensions to scan in build output
const SCANNED_EXTENSIONS = ['.js', '.json', '.html'];

// Files to ignore (source maps, cache metadata)
const IGNORED_FILE_PATTERNS = [
  /\.map$/,            // Source maps
  /build-manifest\.json$/,  // Build metadata
  /middleware-manifest\.json$/,  // Middleware metadata
  /package\.json$/,    // Package metadata
];

let violations = [];
let filesScanned = 0;
let totalBytes = 0;

/**
 * Recursively scan directory for violations
 */
function scanDirectory(dir) {
  if (!fs.existsSync(dir)) {
    console.error(`❌ Build directory not found: ${dir}`);
    console.error('   Run "npm run build" first to create production bundle');
    process.exit(1);
  }

  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      // Recursively scan subdirectories
      scanDirectory(fullPath);
    } else if (entry.isFile()) {
      // Check if file should be scanned
      const ext = path.extname(entry.name);
      if (!SCANNED_EXTENSIONS.includes(ext)) {
        continue;
      }

      // Check if file should be ignored
      const shouldIgnore = IGNORED_FILE_PATTERNS.some(pattern => 
        pattern.test(entry.name)
      );
      if (shouldIgnore) {
        continue;
      }

      // Scan file content
      scanFile(fullPath);
    }
  }
}

/**
 * Scan a single file for forbidden patterns
 */
function scanFile(filePath) {
  filesScanned++;

  const content = fs.readFileSync(filePath, 'utf8');
  totalBytes += content.length;
  const lines = content.split('\n');

  FORBIDDEN_PATTERNS.forEach(({ pattern, name, description }) => {
    const regex = new RegExp(pattern.source, pattern.flags);
    
    lines.forEach((line, index) => {
      const match = regex.exec(line);
      if (match) {
        // Extract context around match (max 80 chars)
        const lineNum = index + 1;
        const matchStart = match.index;
        const contextStart = Math.max(0, matchStart - 40);
        const contextEnd = Math.min(line.length, matchStart + 40);
        const context = line.slice(contextStart, contextEnd);

        violations.push({
          file: path.relative(BUILD_DIR, filePath),
          line: lineNum,
          pattern: name,
          description,
          context: context.trim(),
        });
      }
    });
  });
}

/**
 * Print violations report
 */
function printReport() {
  console.log('\n' + '='.repeat(80));
  console.log('Production Bundle Verification: Exporter Pattern Scan');
  console.log('='.repeat(80));
  console.log(`Build directory: ${BUILD_DIR}`);
  console.log(`Files scanned: ${filesScanned}`);
  console.log(`Total bundle size: ${(totalBytes / 1024 / 1024).toFixed(2)} MB`);
  console.log(`Patterns checked: ${FORBIDDEN_PATTERNS.length}`);
  console.log('='.repeat(80));

  if (violations.length === 0) {
    console.log('\n✅ SUCCESS: No forbidden export patterns found in production bundle');
    console.log('   Tree-shaking successfully removed all export code paths');
    console.log('   Production bundle is clean and secure\n');
    return 0;
  }

  console.log(`\n❌ FAILURE: Found ${violations.length} forbidden pattern(s) in production bundle\n`);
  console.log('This indicates export functionality leaked into production build.');
  console.log('This is a CRITICAL SECURITY ISSUE - exporter patterns must not ship.\n');

  // Group violations by pattern
  const grouped = {};
  violations.forEach(v => {
    if (!grouped[v.pattern]) {
      grouped[v.pattern] = [];
    }
    grouped[v.pattern].push(v);
  });

  Object.entries(grouped).forEach(([pattern, items]) => {
    console.log(`\nPattern: ${pattern}`);
    console.log(`Description: ${items[0].description}`);
    console.log(`Occurrences: ${items.length}`);
    console.log('-'.repeat(80));

    items.slice(0, 5).forEach(({ file, line, context }) => {
      console.log(`  ${file}:${line}`);
      console.log(`    ${context}`);
    });

    if (items.length > 5) {
      console.log(`  ... and ${items.length - 5} more occurrences`);
    }
  });

  console.log('\n' + '='.repeat(80));
  console.log('REMEDIATION STEPS:');
  console.log('='.repeat(80));
  console.log('1. Check if gated code (NODE_ENV !== "production") is tree-shaking correctly');
  console.log('2. Verify Next.js production mode: process.env.NODE_ENV === "production"');
  console.log('3. Search source code for these patterns and ensure they are dev-only');
  console.log('4. Check third-party dependencies for CSV export functionality');
  console.log('5. Re-run: npm run build:prod');
  console.log('6. If issue persists, contact security team\n');

  return 1;
}

/**
 * Main execution
 */
function main() {
  console.log('🔍 Scanning production bundle for forbidden export patterns...');
  console.log(`   Build directory: ${BUILD_DIR}\n`);

  try {
    scanDirectory(BUILD_DIR);
    const exitCode = printReport();
    process.exit(exitCode);
  } catch (error) {
    console.error('\n❌ Fatal error during bundle verification:');
    console.error(error.message);
    console.error(error.stack);
    process.exit(1);
  }
}

// Run if executed directly
if (require.main === module) {
  main();
}

module.exports = { scanDirectory, scanFile, FORBIDDEN_PATTERNS };
