#!/usr/bin/env python3
"""
Test runner script for pronunciation tests.

Provides a convenient way to run pronunciation tests with various options
without needing to remember complex pytest command-line arguments.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --language hindi   # Run Hindi tests only
    python run_tests.py --tag schwa        # Run schwa_deletion tests
    python run_tests.py --coverage         # Generate coverage report
    python run_tests.py --verbose          # Verbose output
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_tests(args):
    """Run tests with the specified options."""
    
    cmd = ['pytest', 'tests/']
    
    # Add verbosity
    if args.verbose:
        cmd.append('-vv')
    elif args.quiet:
        cmd.append('-q')
    else:
        cmd.append('-v')
    
    # Add coverage if requested
    if args.coverage:
        cmd.extend(['--cov=tests', '--cov-report=term-missing'])
        if args.html_coverage:
            cmd.append('--cov-report=html')
    
    # Add language-specific filter
    if args.language:
        cmd.extend(['-k', args.language])
    
    # Add tag filter
    if args.tag:
        if args.language:
            cmd[-1] += f' and {args.tag}'
        else:
            cmd.extend(['-k', args.tag])
    
    # Add specific test file if provided
    if args.file:
        cmd[-1] = Path('tests') / args.file
    
    # Add stop on first failure
    if args.stop_first:
        cmd.append('-x')
    
    # Add parallel execution
    if args.parallel:
        cmd.extend(['-n', 'auto'])
    
    # Add markers
    if args.marker:
        cmd.extend(['-m', args.marker])
    
    # Add JUnit XML output
    if args.junit:
        cmd.append(f'--junit-xml={args.junit}')
    
    # Show test summary
    if not args.no_summary:
        cmd.append('--tb=short')
    
    # Run the tests
    print(f"Running: {' '.join(cmd)}")
    print("-" * 70)
    result = subprocess.run(cmd)
    
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description='Run pronunciation tests for Speak-AI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py                      # Run all tests
  python run_tests.py --language hindi     # Run Hindi tests only
  python run_tests.py --tag schwa          # Run schwa-related tests
  python run_tests.py --coverage           # Generate coverage report
  python run_tests.py -x                   # Stop after first failure
  python run_tests.py --parallel           # Run tests in parallel
        """
    )
    
    # Language selection
    parser.add_argument(
        '--language', '-l',
        choices=['hindi', 'english', 'all'],
        help='Run tests for specific language'
    )
    
    # Test filtering
    parser.add_argument(
        '--tag', '-t',
        help='Run tests with specific tag (e.g., schwa_deletion, geminate)'
    )
    
    parser.add_argument(
        '--file', '-f',
        help='Run specific test file (relative to tests/)'
    )
    
    parser.add_argument(
        '--marker', '-m',
        help='Run tests matching pytest marker'
    )
    
    # Output options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output (very)'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Quiet output'
    )
    
    parser.add_argument(
        '--coverage', '-c',
        action='store_true',
        help='Generate coverage report'
    )
    
    parser.add_argument(
        '--html-coverage',
        action='store_true',
        help='Generate HTML coverage report'
    )
    
    parser.add_argument(
        '--junit',
        metavar='FILE',
        help='Generate JUnit XML report'
    )
    
    # Execution options
    parser.add_argument(
        '-x', '--stop-first',
        action='store_true',
        help='Stop after first failure'
    )
    
    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Run tests in parallel (requires pytest-xdist)'
    )
    
    parser.add_argument(
        '--no-summary',
        action='store_true',
        help='Do not show test summary'
    )
    
    args = parser.parse_args()
    
    # Check if we're in the right directory
    if not Path('tests').is_dir():
        print("Error: tests/ directory not found. Run from project root.")
        sys.exit(1)
    
    # Run tests
    exit_code = run_tests(args)
    
    if exit_code == 0:
        print("-" * 70)
        print("✓ All tests passed!")
    else:
        print("-" * 70)
        print("✗ Some tests failed.")
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
