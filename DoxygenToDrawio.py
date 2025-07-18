#!/usr/bin/env python3
"""
Doxygen to Draw.io Converter

This script directly converts Doxygen output to Draw.io format by:
1. Finding all DOT files in the Doxygen output directory
2. Combining them into a single logical graph
3. Converting to Draw.io XML format with intelligent layout and styling

Supports multiple programming languages and project types.
"""

import os
import re
import glob
import xml.etree.ElementTree as ET
from xml.dom import minidom
import argparse
import sys
import subprocess
import webbrowser
import shutil
import tempfile
from pathlib import Path

# Colors for terminal output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    CYAN = '\033[0;36m'
    WHITE = '\033[1;37m'
    NC = '\033[0m'  # No Color
    
    @staticmethod
    def colored(text, color):
        return f"{color}{text}{Colors.NC}"

class DoxygenToDrawioConverter:
    def __init__(self, doxygen_output_dir="doxygen_output/html", output_file="doxygen_callgraph.drawio", auto_open=False, no_prompt=False, source_dir=None, run_doxygen=False, dot_path=None):
        self.doxygen_output_dir = doxygen_output_dir
        self.output_file = output_file
        self.auto_open = auto_open
        self.no_prompt = no_prompt
        self.source_dir = source_dir or "."  # Default to current directory
        self.run_doxygen = run_doxygen
        self.dot_path = dot_path  # Custom DOT executable path
        self.label_to_simple = {}     # Maps labels to simple IDs (for deduplication)
        self.simple_to_label = {}     # Maps simple IDs to labels
        self.all_edges = []
        self.node_counter = 1
        self.original_to_simple = {}  # Maps original node IDs to simple IDs
        self.file_sources = {}        # Track which files nodes came from
        
    def find_dot_files(self):
        """Find all DOT files in the Doxygen output directory"""
        dot_pattern = os.path.join(self.doxygen_output_dir, "*.dot")
        dot_files = glob.glob(dot_pattern)
        
        if not dot_files:
            print(Colors.colored(f"Error: No .dot files found in '{self.doxygen_output_dir}'.", Colors.RED))
            print("Make sure Doxygen has been run with HAVE_DOT=YES and CALL_GRAPH=YES")
            return []
            
        print(Colors.colored(f"Found {len(dot_files)} DOT files:", Colors.GREEN))
        for dot_file in dot_files:
            print(f"  - {os.path.basename(dot_file)}")
        
        return dot_files
    
    def clean_node_label(self, label, file_source=""):
        """Clean and normalize node labels for multiple programming languages"""
        if not label:
            return f"Node{self.node_counter}"
            
        # Remove escape sequences and clean whitespace
        label = label.replace('\\l', ' ').replace('\n', ' ').strip()
        
        # Remove common Doxygen path prefixes for different project types
        # Generic project patterns
        label = re.sub(r'[^/]+/(?:Core/(?:Inc|Src)/|src/|include/|lib/|bin/|Source/|Headers/)', '', label)
        label = re.sub(r'(?:\.\./)*/(?:src/|include/|lib/|bin/|Source/|Headers/)', '', label)
        label = re.sub(r'.*/(?:src/|include/|lib/|bin/|Source/|Headers/)/', '', label)
        
        # Remove file extensions for multiple languages
        label = re.sub(r'\.(c|h|cpp|hpp|cc|cxx|c\+\+|py|pyx|pyi|java|js|ts|jsx|tsx|go|rs|swift|m|mm|cs|php|rb|pl|sh|asm|s)$', '', label)
        
        # Clean namespace/module separators and special characters
        label = re.sub(r'::', '_', label)  # C++ namespace separator
        label = re.sub(r'\.', '_', label)   # Python module separator, Java package separator
        label = re.sub(r'->', '_', label)   # C pointer operator
        label = re.sub(r'[<>{}\\/:*?"|\[\]()]', '', label)  # Invalid chars and parentheses
        label = re.sub(r'[_]{2,}', '_', label)  # Multiple underscores
        label = label.strip('_')
        
        # Handle special function types
        if label.startswith('__') and label.endswith('__'):
            # Keep Python dunder methods readable but clean
            pass
        elif label.startswith('_'):
            # Handle private methods/functions
            pass
        
        # Handle empty labels after cleaning
        if not label:
            label = f"Node{self.node_counter}"
        
        # Truncate very long labels but keep them meaningful
        if len(label) > 25:
            label = label[:22] + "..."
        
        return label
    
    def find_similar_node(self, clean_label, node_unique_id, file_source):
        """Find if a similar node already exists to avoid duplicates"""
        # First check exact label match
        if clean_label in self.label_to_simple:
            return self.label_to_simple[clean_label]
        
        # Check for very similar labels (fuzzy matching)
        for existing_label, existing_id in self.label_to_simple.items():
            # Check if labels are very similar (accounting for minor variations)
            if self.are_labels_similar(clean_label, existing_label):
                return existing_id
        
        return None
    
    def are_labels_similar(self, label1, label2):
        """Check if two labels represent the same function/node"""
        if label1 == label2:
            return True
        
        # Normalize both labels for comparison
        norm1 = label1.lower().strip('_').replace('_', '').replace('-', '')
        norm2 = label2.lower().strip('_').replace('_', '').replace('-', '')
        
        # Check if one is a substring of the other (for different name variations)
        if norm1 in norm2 or norm2 in norm1:
            # Only consider similar if the difference is not too large
            min_len = min(len(norm1), len(norm2))
            max_len = max(len(norm1), len(norm2))
            if max_len <= min_len * 1.5:  # Allow 50% difference
                return True
        
        # Check for common function name patterns
        # Remove common prefixes/suffixes that might differ
        patterns_to_remove = ['get_', 'set_', 'is_', 'has_', 'do_', 'handle_', 'process_', 'init_', 'setup_', 'create_', 'delete_', 'update_']
        
        clean1 = norm1
        clean2 = norm2
        
        for pattern in patterns_to_remove:
            clean1 = clean1.replace(pattern, '')
            clean2 = clean2.replace(pattern, '')
        
        return clean1 == clean2
    
    def get_execution_priority(self, label, outgoing_count, incoming_count):
        """Calculate execution priority for sequence-based ordering"""
        label_lower = label.lower()
        priority = 0
        
        # Function type priorities (higher = earlier in execution)
        if any(pattern in label_lower for pattern in ['main', '__main__', 'main()', 'int main']):
            priority += 100
        elif any(pattern in label_lower for pattern in ['__init__', 'constructor']):
            priority += 90
        elif any(pattern in label_lower for pattern in ['setup', 'initialize', 'init', 'config']):
            priority += 80
        elif any(pattern in label_lower for pattern in ['start', 'begin', 'run', 'execute']):
            priority += 70
        elif any(pattern in label_lower for pattern in ['process', 'handle', 'update', 'loop']):
            priority += 60
        elif any(pattern in label_lower for pattern in ['read', 'input', 'receive', 'get']):
            priority += 50
        elif any(pattern in label_lower for pattern in ['write', 'output', 'send', 'transmit']):
            priority += 45
        elif any(pattern in label_lower for pattern in ['calculate', 'compute', 'transform']):
            priority += 40
        elif any(pattern in label_lower for pattern in ['validate', 'check', 'verify']):
            priority += 35
        elif any(pattern in label_lower for pattern in ['save', 'store', 'persist']):
            priority += 30
        elif any(pattern in label_lower for pattern in ['cleanup', 'close', 'finalize', 'destroy']):
            priority += 20
        elif any(pattern in label_lower for pattern in ['error', 'fail', 'exception', 'abort']):
            priority += 15
        elif any(pattern in label_lower for pattern in ['test', 'debug', 'trace']):
            priority += 10
        elif any(pattern in label_lower for pattern in ['helper', 'utility', 'util']):
            priority += 5
        
        # Connectivity-based adjustments
        priority += min(20, outgoing_count * 2)  # Functions that call many others are orchestrators
        priority += min(10, incoming_count)      # Popular functions are important
        
        return priority
    
    def refine_levels_by_function_type(self, levels, connected_nodes, incoming, outgoing):
        """Refine level assignments based on functional relationships"""
        # Group functions by type for better organization
        function_groups = {
            'entry': [],      # main, init functions
            'core': [],       # primary business logic
            'io': [],         # input/output operations
            'processing': [], # data processing and computation
            'utility': [],    # helper and utility functions
            'error': [],      # error handling
            'cleanup': []     # cleanup and finalization
        }
        
        # Categorize functions
        for node in connected_nodes:
            label_lower = connected_nodes[node].lower()
            
            if any(pattern in label_lower for pattern in ['main', '__main__', '__init__', 'constructor', 'setup', 'initialize']):
                function_groups['entry'].append(node)
            elif any(pattern in label_lower for pattern in ['error', 'fail', 'exception', 'abort', 'catch']):
                function_groups['error'].append(node)
            elif any(pattern in label_lower for pattern in ['cleanup', 'close', 'finalize', 'destroy', 'delete']):
                function_groups['cleanup'].append(node)
            elif any(pattern in label_lower for pattern in ['read', 'write', 'input', 'output', 'send', 'receive']):
                function_groups['io'].append(node)
            elif any(pattern in label_lower for pattern in ['process', 'calculate', 'compute', 'transform', 'parse']):
                function_groups['processing'].append(node)
            elif any(pattern in label_lower for pattern in ['helper', 'utility', 'util', 'get', 'set']):
                function_groups['utility'].append(node)
            else:
                function_groups['core'].append(node)
        
        # Adjust levels to create logical flow
        # Entry functions should be at the top
        min_entry_level = min([levels.get(node, 0) for node in function_groups['entry']], default=0)
        
        # Error handling functions should be grouped together but not necessarily at the end
        if function_groups['error']:
            error_target_level = max(2, min_entry_level + 2)
            for node in function_groups['error']:
                # Move error handlers closer together but respect dependencies
                if levels.get(node, 0) > error_target_level + 1:
                    # Only move if it doesn't violate dependencies
                    can_move = all(levels.get(parent, 0) < error_target_level for parent in incoming[node])
                    if can_move:
                        levels[node] = error_target_level
        
        # Cleanup functions should generally be later in the flow
        if function_groups['cleanup']:
            cleanup_base_level = max([levels.get(node, 0) for node in connected_nodes]) - 1
            for node in function_groups['cleanup']:
                if levels.get(node, 0) < cleanup_base_level:
                    # Only move if it doesn't violate dependencies
                    can_move = all(levels.get(parent, 0) < cleanup_base_level for parent in incoming[node])
                    if can_move:
                        levels[node] = cleanup_base_level
    
    def get_function_category_order(self, label):
        """Get ordering value for function categories (lower = left, higher = right)"""
        label_lower = label.lower()
        
        # Left to right ordering within a level (execution sequence)
        if any(pattern in label_lower for pattern in ['main', '__main__', 'main()']):
            return 1  # Main functions on the far left
        elif any(pattern in label_lower for pattern in ['__init__', 'constructor', 'setup']):
            return 2  # Initialization functions
        elif any(pattern in label_lower for pattern in ['config', 'configure', 'initialize']):
            return 3  # Configuration functions
        elif any(pattern in label_lower for pattern in ['start', 'begin', 'run', 'execute']):
            return 4  # Execution functions
        elif any(pattern in label_lower for pattern in ['read', 'input', 'receive', 'get']):
            return 5  # Input operations
        elif any(pattern in label_lower for pattern in ['process', 'handle', 'calculate', 'compute']):
            return 6  # Processing functions
        elif any(pattern in label_lower for pattern in ['validate', 'check', 'verify']):
            return 7  # Validation functions
        elif any(pattern in label_lower for pattern in ['write', 'output', 'send', 'transmit']):
            return 8  # Output operations
        elif any(pattern in label_lower for pattern in ['update', 'modify', 'change']):
            return 9  # Update operations
        elif any(pattern in label_lower for pattern in ['save', 'store', 'persist']):
            return 10 # Storage operations
        elif any(pattern in label_lower for pattern in ['timer', 'delay', 'wait', 'sleep']):
            return 11 # Timing operations
        elif any(pattern in label_lower for pattern in ['cleanup', 'close', 'finalize']):
            return 12 # Cleanup operations
        elif any(pattern in label_lower for pattern in ['error', 'fail', 'exception']):
            return 13 # Error handling on the right
        elif any(pattern in label_lower for pattern in ['test', 'debug', 'trace']):
            return 14 # Testing functions
        elif any(pattern in label_lower for pattern in ['helper', 'utility', 'util']):
            return 15 # Utility functions on the far right
        else:
            return 6  # Default to middle (processing category)
    
    def get_edge_style(self, source_label, target_label, source_x, source_y, target_x, target_y):
        """Determine edge style based on execution sequence and function relationships with enhanced routing"""
        
        # Determine flow direction
        is_downward = target_y > source_y
        is_upward = target_y < source_y
        is_lateral = target_y == source_y
        
        # Calculate distances for style decisions
        x_distance = abs(target_x - source_x)
        y_distance = abs(target_y - source_y)
        
        # Determine function relationship types
        is_main_entry = any(keyword in source_label for keyword in ['main', '__main__', 'init', 'setup'])
        is_error_handling = any(keyword in target_label for keyword in ['error', 'fail', 'exception', 'abort'])
        is_utility_call = any(keyword in target_label for keyword in ['get', 'set', 'property', 'util', 'helper'])
        is_io_operation = any(keyword in target_label for keyword in ['read', 'write', 'input', 'output', 'send', 'receive'])
        is_cleanup = any(keyword in target_label for keyword in ['cleanup', 'close', 'finalize', 'destroy'])
        is_timing = any(keyword in target_label for keyword in ['timer', 'delay', 'wait', 'sleep'])
        
        # Enhanced base style with better routing
        base_style = "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;endArrow=classic;shadow=1;labelBackgroundColor=#ffffff;"
        
        # Add connection-specific style based on complexity
        if x_distance > 300 or (is_lateral and x_distance > 200) or (is_upward and x_distance > 150):
            # Complex routing with enhanced waypoints
            routing_style = "entryX=0.5;entryY=0;exitX=0.5;exitY=1;noEdgeStyle=1;"
        else:
            # Simple direct routing
            routing_style = "entryX=0.5;entryY=0;exitX=0.5;exitY=1;"
        
        if is_downward:
            # Main execution flow (top to bottom)
            if is_main_entry:
                # Critical path from main/init functions - thicker, more prominent
                return base_style + routing_style + "strokeWidth=4;strokeColor=#1976d2;fontColor=#1976d2;fontStyle=1;opacity=90;"
            elif is_error_handling:
                # Error handling branches - red dashed
                return base_style + routing_style + "strokeWidth=2.5;strokeColor=#e53e3e;dashed=1;opacity=85;"
            elif is_io_operation:
                # I/O operations flow - purple
                return base_style + routing_style + "strokeWidth=2.5;strokeColor=#9775fa;opacity=85;"
            elif is_cleanup:
                # Cleanup operations - orange dashed
                return base_style + routing_style + "strokeWidth=2;strokeColor=#fd7e14;dashed=1;opacity=80;"
            else:
                # Regular execution flow - blue
                return base_style + routing_style + "strokeWidth=2;strokeColor=#339af0;opacity=85;"
                
        elif is_upward:
            # Feedback, callbacks, or recursive calls - need special visual treatment
            if is_error_handling:
                # Error reporting upward - red curved with high visibility
                return base_style + "edgeStyle=elbowEdgeStyle;elbow=vertical;" + "strokeWidth=2.5;strokeColor=#e53e3e;dashed=1;opacity=80;"
            else:
                # Callbacks, recursion - orange curved
                return base_style + "edgeStyle=elbowEdgeStyle;elbow=vertical;" + "strokeWidth=2;strokeColor=#fd7e14;dashed=1;opacity=75;"
                
        else:  # is_lateral
            # Same-level function calls - use curved routing to avoid overlaps
            curve_style = "edgeStyle=elbowEdgeStyle;elbow=horizontal;" if x_distance > 200 else "edgeStyle=orthogonalEdgeStyle;"
            
            if is_error_handling:
                # Error handling at same level - red
                return base_style + curve_style + "strokeWidth=2;strokeColor=#e53e3e;opacity=80;"
            elif is_utility_call:
                # Utility and helper function calls - green, thinner
                return base_style + curve_style + "strokeWidth=1.5;strokeColor=#37b24d;opacity=75;"
            elif is_timing:
                # Timing and delay calls - salmon
                return base_style + curve_style + "strokeWidth=2;strokeColor=#ff8787;opacity=80;"
            elif is_io_operation:
                # I/O operations at same level - purple
                return base_style + curve_style + "strokeWidth=2;strokeColor=#9775fa;opacity=80;"
            else:
                # Regular peer function calls - teal
                return base_style + curve_style + "strokeWidth=2;strokeColor=#38d9a9;opacity=80;"
    
    def add_execution_waypoints(self, geometry, source_x, source_y, target_x, target_y, 
                               source_label, target_label, max_node_width):
        """Add intelligent waypoints for better execution flow visualization with node collision avoidance"""
        
        # Calculate distances and decide if waypoints are needed
        x_distance = abs(target_x - source_x)
        y_distance = abs(target_y - source_y)
        
        # Estimate node dimensions for collision avoidance
        node_width = max_node_width
        node_height = 80  # Estimated average node height
        
        # Add buffer space around nodes
        buffer_x = 30
        buffer_y = 20
        
        waypoints = []
        
        # Determine connection type and optimal routing
        if target_y == source_y:
            # Same level (horizontal) connections
            self._add_horizontal_waypoints(waypoints, source_x, source_y, target_x, target_y, 
                                         source_label, target_label, node_width, node_height, 
                                         buffer_x, buffer_y)
        elif target_y > source_y:
            # Downward flow (normal execution)
            self._add_downward_waypoints(waypoints, source_x, source_y, target_x, target_y,
                                       source_label, target_label, node_width, node_height,
                                       buffer_x, buffer_y, x_distance, y_distance)
        else:
            # Upward flow (callbacks, recursion)
            self._add_upward_waypoints(waypoints, source_x, source_y, target_x, target_y,
                                     source_label, target_label, node_width, node_height,
                                     buffer_x, buffer_y, x_distance, y_distance)
        
        # Add waypoints to geometry if any were created
        if waypoints:
            array = ET.SubElement(geometry, 'Array')
            array.set('as', 'points')
            
            for waypoint_x, waypoint_y in waypoints:
                point = ET.SubElement(array, 'mxPoint', x=str(int(waypoint_x)), y=str(int(waypoint_y)))
    
    def _add_horizontal_waypoints(self, waypoints, source_x, source_y, target_x, target_y,
                                source_label, target_label, node_width, node_height, buffer_x, buffer_y):
        """Add waypoints for horizontal (same-level) connections"""
        x_distance = abs(target_x - source_x)
        
        # Only add waypoints for longer horizontal connections
        if x_distance > node_width * 1.5:
            # Determine routing preference based on function type
            route_above = True  # Default to routing above
            offset_y = -50  # Default offset above nodes
            
            if any(keyword in target_label for keyword in ['error', 'fail', 'exception']):
                route_above = True
                offset_y = -60  # Route error calls higher above
            elif any(keyword in target_label for keyword in ['cleanup', 'finalize', 'destroy']):
                route_above = False
                offset_y = 60  # Route cleanup calls below
            elif any(keyword in target_label for keyword in ['util', 'helper', 'get', 'set']):
                route_above = True
                offset_y = -40  # Route utility calls slightly above
            
            # Calculate waypoint positions
            if x_distance > node_width * 3:
                # Long horizontal connection - use multiple waypoints for smoother curve
                quarter_x = source_x + (target_x - source_x) * 0.25
                mid_x = source_x + (target_x - source_x) * 0.5
                three_quarter_x = source_x + (target_x - source_x) * 0.75
                
                waypoint_y = source_y + offset_y
                
                waypoints.extend([
                    (quarter_x, waypoint_y),
                    (mid_x, waypoint_y),
                    (three_quarter_x, waypoint_y)
                ])
            else:
                # Medium horizontal connection - use single waypoint
                mid_x = source_x + (target_x - source_x) * 0.5
                waypoint_y = source_y + offset_y
                waypoints.append((mid_x, waypoint_y))
    
    def _add_downward_waypoints(self, waypoints, source_x, source_y, target_x, target_y,
                              source_label, target_label, node_width, node_height, 
                              buffer_x, buffer_y, x_distance, y_distance):
        """Add waypoints for downward (normal execution) flow"""
        
        # For large horizontal offsets in downward flow, create stepped routing
        if x_distance > node_width * 2:
            # Step down and across to avoid crossing other nodes
            
            # First waypoint: step down from source
            waypoint1_x = source_x
            waypoint1_y = source_y + node_height + buffer_y
            
            # Second waypoint: move horizontally at intermediate level
            waypoint2_x = target_x
            waypoint2_y = waypoint1_y
            
            # Third waypoint: step down to target level if there's still distance
            if y_distance > (node_height + buffer_y * 2):
                waypoint3_x = target_x
                waypoint3_y = target_y - node_height // 2 - buffer_y
                waypoints.extend([
                    (waypoint1_x, waypoint1_y),
                    (waypoint2_x, waypoint2_y),
                    (waypoint3_x, waypoint3_y)
                ])
            else:
                waypoints.extend([
                    (waypoint1_x, waypoint1_y),
                    (waypoint2_x, waypoint2_y)
                ])
        elif x_distance > node_width * 0.8:
            # Medium horizontal offset - single intermediate waypoint
            mid_x = source_x + (target_x - source_x) * 0.7
            mid_y = source_y + y_distance * 0.6
            waypoints.append((mid_x, mid_y))
    
    def _add_upward_waypoints(self, waypoints, source_x, source_y, target_x, target_y,
                            source_label, target_label, node_width, node_height,
                            buffer_x, buffer_y, x_distance, y_distance):
        """Add waypoints for upward (callback/recursion) flow"""
        
        # Upward flow needs special handling to avoid crossing nodes
        if x_distance > node_width:
            # Route around the side to avoid crossing intermediate nodes
            
            # Determine which side to route around based on horizontal distance
            if target_x > source_x:
                # Target is to the right - route right and up
                side_offset = node_width + buffer_x * 2
                waypoint1_x = source_x + side_offset
            else:
                # Target is to the left - route left and up  
                side_offset = node_width + buffer_x * 2
                waypoint1_x = source_x - side_offset
            
            # First waypoint: move to the side
            waypoint1_y = source_y
            
            # Second waypoint: move up to target level
            waypoint2_x = waypoint1_x
            waypoint2_y = target_y
            
            # Third waypoint: move horizontally to target
            waypoint3_x = target_x
            waypoint3_y = target_y
            
            waypoints.extend([
                (waypoint1_x, waypoint1_y),
                (waypoint2_x, waypoint2_y),
                (waypoint3_x, waypoint3_y)
            ])
        else:
            # Short upward connection - simple curved path
            mid_x = source_x + (target_x - source_x) * 0.5
            
            # Route below source and above target for smooth curve
            curve_offset = 40
            waypoint1_y = source_y + curve_offset
            waypoint2_y = target_y - curve_offset
            
            waypoints.extend([
                (mid_x, waypoint1_y),
                (mid_x, waypoint2_y)
            ])
    
    def check_doxygen_available(self):
        """Check if Doxygen is available in the system"""
        try:
            result = subprocess.run(['doxygen', '--version'], 
                                  capture_output=True, text=True, check=True)
            version = result.stdout.strip()
            print(Colors.colored(f"✅ Found Doxygen {version}", Colors.GREEN))
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(Colors.colored("❌ Doxygen not found in system PATH", Colors.RED))
            print("Please install Doxygen:")
            print("  macOS: brew install doxygen")
            print("  Ubuntu/Debian: sudo apt-get install doxygen")
            print("  Windows: Download from doxygen.nl")
            return False
    
    def check_dot_available(self):
        """Check if Graphviz DOT is available and get its path"""
        dot_paths_to_check = [
            'dot',  # System PATH
            '/usr/bin/dot',  # Common Linux location
            '/usr/local/bin/dot',  # Common macOS homebrew location
            '/opt/homebrew/bin/dot',  # Apple Silicon homebrew location
            'C:\\Program Files\\Graphviz\\bin\\dot.exe',  # Windows default
            'C:\\Program Files (x86)\\Graphviz\\bin\\dot.exe',  # Windows x86
        ]
        
        # Check if user provided a custom DOT path
        if self.dot_path:
            dot_paths_to_check.insert(0, self.dot_path)
        
        for dot_path in dot_paths_to_check:
            try:
                result = subprocess.run([dot_path, '-V'], 
                                      capture_output=True, text=True, check=True)
                # DOT version info goes to stderr, not stdout
                version_info = result.stderr.strip()
                print(Colors.colored(f"✅ Found Graphviz DOT: {version_info}", Colors.GREEN))
                print(Colors.colored(f"📍 DOT path: {dot_path}", Colors.CYAN))
                return dot_path
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        print(Colors.colored("❌ Graphviz DOT not found in system PATH", Colors.RED))
        print(Colors.colored("📝 DOT is required for generating call graphs", Colors.YELLOW))
        print("\nPlease install Graphviz:")
        print("  macOS: brew install graphviz")
        print("  Ubuntu/Debian: sudo apt-get install graphviz")
        print("  Windows: Download from graphviz.org")
        print("\nOr specify DOT path with --dot-path option")
        print("Common DOT locations to check:")
        print("  /usr/bin/dot")
        print("  /usr/local/bin/dot")
        print("  /opt/homebrew/bin/dot (Apple Silicon Mac)")
        print("  C:\\Program Files\\Graphviz\\bin\\dot.exe (Windows)")
        print("\nTo find DOT on your system, try:")
        print("  which dot        (Linux/macOS)")
        print("  where dot        (Windows)")
        return None
    
    def find_doxyfile(self):
        """Find existing Doxyfile in the source directory"""
        possible_names = ['Doxyfile', 'Doxyfile.in', 'doxyfile', 'doxygen.conf', 'doxygen.cfg']
        
        for name in possible_names:
            doxyfile_path = os.path.join(self.source_dir, name)
            if os.path.exists(doxyfile_path):
                print(Colors.colored(f"📄 Found existing Doxyfile: {doxyfile_path}", Colors.GREEN))
                return doxyfile_path
        
        return None
    
    def create_doxyfile(self, dot_executable_path=None):
        """Create a basic Doxyfile optimized for call graph generation"""
        doxyfile_path = os.path.join(self.source_dir, "Doxyfile")
        
        # Calculate the correct output directory
        # If doxygen_output_dir ends with /html, use the parent directory
        # Otherwise, use doxygen_output_dir directly
        if self.doxygen_output_dir.endswith('/html') or self.doxygen_output_dir.endswith('\\html'):
            doxygen_output_base = os.path.dirname(self.doxygen_output_dir)
        else:
            doxygen_output_base = self.doxygen_output_dir
        
        # Ensure we have a valid output directory
        if not doxygen_output_base:
            doxygen_output_base = "doxygen_output"
        
        # Convert to absolute path to ensure it's created in the current directory, not source directory
        if not os.path.isabs(doxygen_output_base):
            # Get the current working directory (where the script was called from)
            current_dir = os.getcwd()
            doxygen_output_base = os.path.join(current_dir, doxygen_output_base)
        
        # Normalize the path for consistent directory separators
        doxygen_output_base = os.path.normpath(doxygen_output_base)
        
        # Detect source file extensions in the directory
        source_extensions = set()
        common_extensions = ['.c', '.cpp', '.cxx', '.cc', '.h', '.hpp', '.hxx', '.py', '.java', '.js', '.ts']
        
        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in common_extensions:
                    source_extensions.add(ext)
        
        # Determine project type based on files found
        if '.py' in source_extensions:
            project_type = "Python"
            file_patterns = "*.py"
        elif any(ext in source_extensions for ext in ['.cpp', '.cxx', '.cc', '.hpp', '.hxx']):
            project_type = "C++"
            file_patterns = "*.cpp *.cxx *.cc *.hpp *.hxx *.h"
        elif any(ext in source_extensions for ext in ['.c', '.h']):
            project_type = "C"
            file_patterns = "*.c *.h"
        elif '.java' in source_extensions:
            project_type = "Java"
            file_patterns = "*.java"
        elif any(ext in source_extensions for ext in ['.js', '.ts']):
            project_type = "JavaScript/TypeScript"
            file_patterns = "*.js *.ts"
        else:
            project_type = "Multi-language"
            file_patterns = " ".join(f"*{ext}" for ext in source_extensions)
        
        project_name = os.path.basename(os.path.abspath(self.source_dir))
        
        # Set DOT path if provided
        if dot_executable_path and os.path.dirname(dot_executable_path):
            dot_path_line = f"DOT_PATH               = {os.path.dirname(dot_executable_path)}"
        else:
            dot_path_line = "DOT_PATH               ="
        
        doxyfile_content = f'''# Doxyfile generated by Doxygen-to-Drawio Converter
# Project: {project_name} ({project_type})

#---------------------------------------------------------------------------
# Project related configuration options
#---------------------------------------------------------------------------
DOXYFILE_ENCODING      = UTF-8
PROJECT_NAME           = "{project_name}"
PROJECT_NUMBER         = "1.0"
PROJECT_BRIEF          = "Automatically generated documentation"
OUTPUT_DIRECTORY       = {doxygen_output_base}
CREATE_SUBDIRS         = NO
ALLOW_UNICODE_NAMES    = NO
OUTPUT_LANGUAGE        = English
BRIEF_MEMBER_DESC      = YES
REPEAT_BRIEF           = YES
ABBREVIATE_BRIEF       = 
ALWAYS_DETAILED_SEC    = NO
INLINE_INHERITED_MEMB  = NO
FULL_PATH_NAMES        = YES
STRIP_FROM_PATH        = 
STRIP_FROM_INC_PATH    = 
SHORT_NAMES            = NO
JAVADOC_AUTOBRIEF      = NO
JAVADOC_BANNER         = NO
QT_AUTOBRIEF           = NO
MULTILINE_CPP_IS_BRIEF = NO
PYTHON_DOCSTRING       = YES
INHERIT_DOCS           = YES
SEPARATE_MEMBER_PAGES  = NO
TAB_SIZE               = 4
ALIASES                = 
OPTIMIZE_OUTPUT_FOR_C  = {'YES' if project_type == 'C' else 'NO'}
OPTIMIZE_OUTPUT_JAVA   = {'YES' if project_type == 'Java' else 'NO'}
OPTIMIZE_FOR_FORTRAN   = NO
OPTIMIZE_OUTPUT_VHDL   = NO
OPTIMIZE_OUTPUT_SLICE  = NO
EXTENSION_MAPPING      = 
MARKDOWN_SUPPORT       = YES
TOC_INCLUDE_HEADINGS   = 5
AUTOLINK_SUPPORT       = YES
BUILTIN_STL_SUPPORT    = YES
CPP_CLI_SUPPORT        = NO
SIP_SUPPORT            = NO
IDL_PROPERTY_SUPPORT   = YES
DISTRIBUTE_GROUP_DOC   = NO
GROUP_NESTED_COMPOUNDS = NO
SUBGROUPING            = YES
INLINE_GROUPED_CLASSES = NO
INLINE_SIMPLE_STRUCTS  = NO
TYPEDEF_HIDES_STRUCT   = NO
LOOKUP_CACHE_SIZE      = 0

#---------------------------------------------------------------------------
# Build related configuration options
#---------------------------------------------------------------------------
EXTRACT_ALL            = YES
EXTRACT_PRIVATE        = YES
EXTRACT_PRIV_VIRTUAL   = NO
EXTRACT_PACKAGE        = NO
EXTRACT_STATIC         = YES
EXTRACT_LOCAL_CLASSES  = YES
EXTRACT_LOCAL_METHODS  = NO
EXTRACT_ANON_NSPACES   = NO
HIDE_UNDOC_MEMBERS     = NO
HIDE_UNDOC_CLASSES     = NO
HIDE_FRIEND_COMPOUNDS  = NO
HIDE_IN_BODY_DOCS      = NO
INTERNAL_DOCS          = NO
CASE_SENSE_NAMES       = {'YES' if project_type != 'Windows' else 'NO'}
HIDE_SCOPE_NAMES       = NO
HIDE_COMPOUND_REFERENCE= NO
SHOW_INCLUDE_FILES     = YES
SHOW_GROUPED_MEMB_INC  = NO
FORCE_LOCAL_INCLUDES   = NO
INLINE_INFO            = YES
SORT_MEMBER_DOCS       = YES
SORT_BRIEF_DOCS        = NO
SORT_MEMBERS_CTORS_1ST = NO
SORT_GROUP_NAMES       = NO
SORT_BY_SCOPE_NAME     = NO
STRICT_PROTO_MATCHING  = NO
GENERATE_TODOLIST      = YES
GENERATE_TESTLIST      = YES
GENERATE_BUGLIST       = YES
GENERATE_DEPRECATEDLIST= YES
ENABLED_SECTIONS       = 
MAX_INITIALIZER_LINES  = 30
SHOW_USED_FILES        = YES
SHOW_FILES             = YES
SHOW_NAMESPACES        = YES
FILE_VERSION_FILTER    = 
LAYOUT_FILE            = 
CITE_BIB_FILES         = 

#---------------------------------------------------------------------------
# Configuration options related to warning and progress messages
#---------------------------------------------------------------------------
QUIET                  = NO
WARNINGS               = YES
WARN_IF_UNDOCUMENTED   = YES
WARN_IF_DOC_ERROR      = YES
WARN_NO_PARAMDOC       = NO
WARN_AS_ERROR          = NO
WARN_FORMAT            = "$file:$line: $text"
WARN_LOGFILE           = 

#---------------------------------------------------------------------------
# Configuration options related to the input files
#---------------------------------------------------------------------------
INPUT                  = {self.source_dir}
INPUT_ENCODING         = UTF-8
FILE_PATTERNS          = {file_patterns}
RECURSIVE              = YES
EXCLUDE                = 
EXCLUDE_SYMLINKS       = NO
EXCLUDE_PATTERNS       = */build/* */dist/* */.git/* */node_modules/* */__pycache__/* *.tmp */.DS_Store
EXCLUDE_SYMBOLS        = 
EXAMPLE_PATH           = 
EXAMPLE_PATTERNS       = 
EXAMPLE_RECURSIVE      = NO
IMAGE_PATH             = 
INPUT_FILTER           = 
FILTER_PATTERNS        = 
FILTER_SOURCE_FILES    = NO
FILTER_SOURCE_PATTERNS = 
USE_MDFILE_AS_MAINPAGE = 

#---------------------------------------------------------------------------
# Configuration options related to source browsing
#---------------------------------------------------------------------------
SOURCE_BROWSER         = YES
INLINE_SOURCES         = NO
STRIP_CODE_COMMENTS    = YES
REFERENCED_BY_RELATION = YES
REFERENCES_RELATION    = YES
REFERENCES_LINK_SOURCE = YES
SOURCE_TOOLTIPS        = YES
USE_HTAGS              = NO
VERBATIM_HEADERS       = YES
CLANG_ASSISTED_PARSING = NO
CLANG_OPTIONS          = 
CLANG_DATABASE_PATH    = 

#---------------------------------------------------------------------------
# Configuration options related to the alphabetical class index
#---------------------------------------------------------------------------
ALPHABETICAL_INDEX     = YES
COLS_IN_ALPHA_INDEX    = 5
IGNORE_PREFIX          = 

#---------------------------------------------------------------------------
# Configuration options related to the HTML output
#---------------------------------------------------------------------------
GENERATE_HTML          = YES
HTML_OUTPUT            = html
HTML_FILE_EXTENSION    = .html
HTML_HEADER            = 
HTML_FOOTER            = 
HTML_STYLESHEET        = 
HTML_EXTRA_STYLESHEET  = 
HTML_EXTRA_FILES       = 
HTML_COLORSTYLE_HUE    = 220
HTML_COLORSTYLE_SAT    = 100
HTML_COLORSTYLE_GAMMA  = 80
HTML_TIMESTAMP         = NO
HTML_DYNAMIC_MENUS     = YES
HTML_DYNAMIC_SECTIONS  = NO
HTML_INDEX_NUM_ENTRIES = 100
GENERATE_DOCSET        = NO
DOCSET_FEEDNAME        = "Doxygen generated docs"
DOCSET_BUNDLE_ID       = org.doxygen.Project
DOCSET_PUBLISHER_ID    = org.doxygen.Publisher
DOCSET_PUBLISHER_NAME  = Publisher
GENERATE_HTMLHELP      = NO
CHM_FILE               = 
HHC_LOCATION           = 
GENERATE_CHI           = NO
CHM_INDEX_ENCODING     = 
BINARY_TOC             = NO
TOC_EXPAND             = NO
GENERATE_QHP           = NO
QCH_FILE               = 
QHP_NAMESPACE          = org.doxygen.Project
QHP_VIRTUAL_FOLDER     = doc
QHP_CUST_FILTER_NAME   = 
QHP_CUST_FILTER_ATTRS  = 
QHP_SECT_FILTER_ATTRS  = 
QHG_LOCATION           = 
GENERATE_ECLIPSEHELP   = NO
ECLIPSE_DOC_ID         = org.doxygen.Project
DISABLE_INDEX          = NO
GENERATE_TREEVIEW      = NO
ENUM_VALUES_PER_LINE   = 4
TREEVIEW_WIDTH         = 250
EXT_LINKS_IN_WINDOW    = NO
FORMULA_FONTSIZE       = 10
FORMULA_TRANSPARENT    = YES
FORMULA_MACROFILE      = 
USE_MATHJAX            = NO
MATHJAX_FORMAT         = HTML-CSS
MATHJAX_RELPATH        = https://cdn.jsdelivr.net/npm/mathjax@2
MATHJAX_EXTENSIONS     = 
MATHJAX_CODEFILE       = 
SEARCHENGINE           = YES
SERVER_BASED_SEARCH    = NO
EXTERNAL_SEARCH        = NO
SEARCHENGINE_URL       = 
SEARCHDATA_FILE        = searchdata.xml
EXTERNAL_SEARCH_ID     = 
EXTRA_SEARCH_MAPPINGS  = 

#---------------------------------------------------------------------------
# Configuration options related to the LaTeX output
#---------------------------------------------------------------------------
GENERATE_LATEX         = NO

#---------------------------------------------------------------------------
# Configuration options related to the RTF output
#---------------------------------------------------------------------------
GENERATE_RTF           = NO

#---------------------------------------------------------------------------
# Configuration options related to the man page output
#---------------------------------------------------------------------------
GENERATE_MAN           = NO

#---------------------------------------------------------------------------
# Configuration options related to the XML output
#---------------------------------------------------------------------------
GENERATE_XML           = NO

#---------------------------------------------------------------------------
# Configuration options related to the DOCBOOK output
#---------------------------------------------------------------------------
GENERATE_DOCBOOK       = NO

#---------------------------------------------------------------------------
# Configuration options for the AutoGen Definitions output
#---------------------------------------------------------------------------
GENERATE_AUTOGEN_DEF   = NO

#---------------------------------------------------------------------------
# Configuration options related to the Perl module output
#---------------------------------------------------------------------------
GENERATE_PERLMOD       = NO

#---------------------------------------------------------------------------
# Configuration options related to the preprocessor
#---------------------------------------------------------------------------
ENABLE_PREPROCESSING   = YES
MACRO_EXPANSION        = NO
EXPAND_ONLY_PREDEF     = NO
SEARCH_INCLUDES        = YES
INCLUDE_PATH           = 
INCLUDE_FILE_PATTERNS  = 
PREDEFINED             = 
EXPAND_AS_DEFINED      = 
SKIP_FUNCTION_MACROS   = YES

#---------------------------------------------------------------------------
# Configuration options related to external references
#---------------------------------------------------------------------------
TAGFILES               = 
GENERATE_TAGFILE       = 
ALLEXTERNALS           = NO
EXTERNAL_GROUPS        = YES
EXTERNAL_PAGES         = YES

#---------------------------------------------------------------------------
# Configuration options related to the dot tool (CRITICAL FOR CALL GRAPHS)
#---------------------------------------------------------------------------
CLASS_DIAGRAMS         = YES
DIA_PATH               = 
HIDE_UNDOC_RELATIONS   = YES
HAVE_DOT               = {'YES' if dot_executable_path else 'NO'}
DOT_NUM_THREADS        = 0
DOT_FONTNAME           = Helvetica
DOT_FONTSIZE           = 10
DOT_FONTPATH           = 
{dot_path_line}
CLASS_GRAPH            = YES
COLLABORATION_GRAPH    = YES
GROUP_GRAPHS           = YES
UML_LOOK               = NO
UML_LIMIT_NUM_FIELDS   = 10
TEMPLATE_RELATIONS     = NO
INCLUDE_GRAPH          = YES
INCLUDED_BY_GRAPH      = YES
CALL_GRAPH             = {'YES' if dot_executable_path else 'NO'}
CALLER_GRAPH           = {'YES' if dot_executable_path else 'NO'}
GRAPHICAL_HIERARCHY    = YES
DIRECTORY_GRAPH        = YES
DOT_IMAGE_FORMAT       = png
INTERACTIVE_SVG        = NO
DOTFILE_DIRS           = 
MSCFILE_DIRS           = 
DIAFILE_DIRS           = 
PLANTUML_JAR_PATH      = 
PLANTUML_CFG_FILE      = 
PLANTUML_INCLUDE_PATH  = 
DOT_GRAPH_MAX_NODES    = 50
MAX_DOT_GRAPH_DEPTH    = 0
DOT_TRANSPARENT        = NO
DOT_MULTI_TARGETS      = NO
GENERATE_LEGEND        = YES
DOT_CLEANUP            = NO
'''
        
        try:
            with open(doxyfile_path, 'w', encoding='utf-8') as f:
                f.write(doxyfile_content)
            print(Colors.colored(f"📝 Created Doxyfile: {doxyfile_path}", Colors.GREEN))
            print(Colors.colored(f"🎯 Optimized for {project_type} project with call graph generation", Colors.CYAN))
            if dot_executable_path:
                print(Colors.colored(f"🔗 Configured with DOT path: {dot_executable_path}", Colors.CYAN))
            else:
                print(Colors.colored(f"⚠️  Call graphs disabled - DOT not found", Colors.YELLOW))
            return doxyfile_path
        except IOError as e:
            print(Colors.colored(f"❌ Error creating Doxyfile: {e}", Colors.RED))
            return None
    
    def update_doxyfile_for_callgraph(self, doxyfile_path, dot_executable_path=None):
        """Update existing Doxyfile to ensure call graph generation is enabled"""
        print(Colors.colored(f"🔧 Updating Doxyfile for call graph generation...", Colors.YELLOW))
        
        try:
            with open(doxyfile_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Critical settings for call graph generation
            updates = {
                'HAVE_DOT': 'YES' if dot_executable_path else 'NO',
                'CALL_GRAPH': 'YES' if dot_executable_path else 'NO',
                'CALLER_GRAPH': 'YES' if dot_executable_path else 'NO',
                'DOT_CLEANUP': 'NO',  # Keep DOT files for conversion
                'EXTRACT_ALL': 'YES',
                'SOURCE_BROWSER': 'YES',
                'GENERATE_HTML': 'YES',
                'REFERENCED_BY_RELATION': 'YES',
                'REFERENCES_RELATION': 'YES'
            }
            
            # Add DOT_PATH if we have a custom DOT executable
            if dot_executable_path and os.path.dirname(dot_executable_path):
                updates['DOT_PATH'] = os.path.dirname(dot_executable_path)
            else:
                updates['DOT_PATH'] = ""  # Ensure DOT_PATH is empty if no DOT found
            
            modified = False
            for setting, value in updates.items():
                # Look for the setting in the file
                pattern = rf'^(\s*{setting}\s*=\s*).*$'
                replacement = f'\\g<1>{value}'
                
                new_content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)
                if count > 0:
                    content = new_content
                    modified = True
                    print(f"  ✓ Updated {setting} = {value}")
                else:
                    # Setting not found, add it
                    content += f'\n{setting} = {value}\n'
                    modified = True
                    print(f"  + Added {setting} = {value}")
            
            if modified:
                # Create backup
                backup_path = doxyfile_path + '.backup'
                shutil.copy2(doxyfile_path, backup_path)
                print(f"  💾 Backup created: {backup_path}")
                
                # Write updated content
                with open(doxyfile_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(Colors.colored(f"✅ Doxyfile updated successfully", Colors.GREEN))
                if dot_executable_path:
                    print(Colors.colored(f"🔗 Configured with DOT path: {dot_executable_path}", Colors.CYAN))
                else:
                    print(Colors.colored(f"⚠️  Call graphs disabled - DOT not available", Colors.YELLOW))
            else:
                print(Colors.colored(f"✅ Doxyfile already optimized for call graphs", Colors.GREEN))
                
            return True
            
        except IOError as e:
            print(Colors.colored(f"❌ Error updating Doxyfile: {e}", Colors.RED))
            return False
    
    def run_doxygen_process(self, doxyfile_path):
        """Run Doxygen to generate documentation and call graphs"""
        print(Colors.colored(f"🚀 Running Doxygen...", Colors.YELLOW))
        
        try:
            # Change to the directory containing the Doxyfile
            work_dir = os.path.dirname(doxyfile_path) or self.source_dir
            doxyfile_name = os.path.basename(doxyfile_path)
            
            # Run Doxygen
            result = subprocess.run(
                ['doxygen', doxyfile_name],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                print(Colors.colored(f"✅ Doxygen completed successfully", Colors.GREEN))
                
                # Check for warnings
                if result.stderr:
                    warning_lines = [line for line in result.stderr.split('\n') if line.strip()]
                    if warning_lines:
                        print(Colors.colored(f"⚠️  Doxygen warnings:", Colors.YELLOW))
                        for line in warning_lines[:5]:  # Show first 5 warnings
                            print(f"  {line}")
                        if len(warning_lines) > 5:
                            print(f"  ... and {len(warning_lines) - 5} more warnings")
                
                # Update output directory to point to generated files
                # Calculate the expected output path based on doxygen_output_dir
                if self.doxygen_output_dir.endswith('/html') or self.doxygen_output_dir.endswith('\\html'):
                    doxygen_output_base = os.path.dirname(self.doxygen_output_dir)
                    expected_html_dir = self.doxygen_output_dir
                else:
                    doxygen_output_base = self.doxygen_output_dir
                    expected_html_dir = os.path.join(self.doxygen_output_dir, 'html')
                
                # Convert to absolute path if relative - use current working directory, not source directory
                if not os.path.isabs(expected_html_dir):
                    current_dir = os.getcwd()
                    expected_html_dir = os.path.join(current_dir, expected_html_dir)
                if not os.path.isabs(doxygen_output_base):
                    current_dir = os.getcwd()
                    doxygen_output_base = os.path.join(current_dir, doxygen_output_base)
                
                if os.path.exists(expected_html_dir):
                    self.doxygen_output_dir = expected_html_dir
                    print(Colors.colored(f"📁 Doxygen output: {expected_html_dir}", Colors.CYAN))
                    return True
                else:
                    print(Colors.colored(f"❌ Expected output directory not found: {expected_html_dir}", Colors.RED))
                    # Try to list what was actually created
                    abs_base = doxygen_output_base  # Already converted to absolute path above
                    
                    if os.path.exists(abs_base):
                        print(f"Available directories in {abs_base}:")
                        try:
                            for item in os.listdir(abs_base):
                                item_path = os.path.join(abs_base, item)
                                if os.path.isdir(item_path):
                                    print(f"  - {item}/")
                        except OSError:
                            pass
                    return False
            else:
                print(Colors.colored(f"❌ Doxygen failed with return code {result.returncode}", Colors.RED))
                if result.stderr:
                    print("Error output:")
                    print(result.stderr)
                return False
                
        except subprocess.TimeoutExpired:
            print(Colors.colored(f"❌ Doxygen timed out after 5 minutes", Colors.RED))
            return False
        except FileNotFoundError:
            print(Colors.colored(f"❌ Doxygen executable not found", Colors.RED))
            return False
        except Exception as e:
            print(Colors.colored(f"❌ Error running Doxygen: {e}", Colors.RED))
            return False
    
    def setup_doxygen(self):
        """Setup and run Doxygen if needed"""
        print(Colors.colored("\n🔍 Setting up Doxygen integration...", Colors.BLUE))
        
        # Check if Doxygen is available
        if not self.check_doxygen_available():
            return False
        
        # Check if DOT is available
        dot_executable_path = self.check_dot_available()
        
        if not dot_executable_path:
            print(Colors.colored("\n⚠️  Warning: DOT not found - call graphs will be disabled", Colors.YELLOW))
            print("The script will still generate documentation, but without call graph diagrams.")
            
            if not self.no_prompt:
                try:
                    response = input(Colors.colored("Continue without call graphs? (y/n): ", Colors.YELLOW)).lower().strip()
                    if response not in ['y', 'yes', '1', 'true']:
                        print("Please install Graphviz or specify DOT path with --dot-path")
                        return False
                except (KeyboardInterrupt, EOFError):
                    print("\nAborted by user.")
                    return False
        
        # Look for existing Doxyfile
        doxyfile_path = self.find_doxyfile()
        
        if doxyfile_path:
            # Update existing Doxyfile for call graph generation
            if not self.update_doxyfile_for_callgraph(doxyfile_path, dot_executable_path):
                return False
        else:
            # Create new Doxyfile
            print(Colors.colored(f"📝 No Doxyfile found, creating one...", Colors.YELLOW))
            doxyfile_path = self.create_doxyfile(dot_executable_path)
            if not doxyfile_path:
                return False
        
        # Run Doxygen
        if not self.run_doxygen_process(doxyfile_path):
            return False
        
        print(Colors.colored(f"✅ Doxygen setup complete!", Colors.GREEN))
        
        # Check if we actually got DOT files for call graphs
        if dot_executable_path:
            dot_files = glob.glob(os.path.join(self.doxygen_output_dir, "*.dot"))
            if not dot_files:
                print(Colors.colored(f"⚠️  Warning: No DOT files generated despite DOT being available", Colors.YELLOW))
                print("This might be because your source code doesn't have function calls,")
                print("or the DOT graph limits were exceeded. The script will continue with")
                print("documentation structure instead of call graphs.")
        
        return True
    
    def process_single_dot_file(self, dot_file_path):
        """Process a single DOT file and extract nodes and edges"""
        try:
            with open(dot_file_path, 'r', encoding='utf-8') as file:
                content = file.read()
        except (UnicodeDecodeError, IOError) as e:
            print(f"Warning: Could not read {dot_file_path}: {e}")
            return
        
        # Check if file contains valid digraph content
        if not re.search(r'digraph\s+', content):
            print(f"Warning: {dot_file_path} does not appear to be a valid DOT file. Skipping.")
            return
        
        file_basename = os.path.basename(dot_file_path)
        print(f"Processing: {file_basename}")
        
        # Skip directory dependency graphs - focus on function call graphs
        if 'dep.dot' in file_basename or 'dir_' in file_basename:
            print(f"  Skipping directory dependency graph: {file_basename}")
            return
        
        # Extract nodes with comprehensive pattern matching for function call graphs
        # Handle various Doxygen DOT formats for function nodes
        node_patterns = [
            # Standard Doxygen function node format: Node1 [id="Node000001",label="function_name"...]
            re.compile(r'(Node\d+)\s*\[id="([^"]*)",\s*label="([^"]+)"[^]]*\]', re.DOTALL),
            # Alternative format: NodeName [label="function_name"...]
            re.compile(r'(\w+)\s*\[\s*label="([^"]+)"[^]]*\]', re.DOTALL),
            # More comprehensive format with id and label
            re.compile(r'(\w+)\s*\[\s*id="([^"]*)"[^]]*label="([^"]+)"[^]]*\]', re.DOTALL),
            # Handle nodes without explicit id field
            re.compile(r'(\w+)\s*\[([^]]*label="([^"]+)")[^]]*\]', re.DOTALL)
        ]
        
        nodes_found = 0
        processed_nodes = set()  # Avoid duplicates within the same file
        
        for pattern_idx, pattern in enumerate(node_patterns):
            for match in pattern.finditer(content):
                groups = match.groups()
                
                if pattern_idx == 0:  # Standard Node format
                    original_node_id, node_unique_id, node_label = groups
                elif pattern_idx == 1:  # Simple label format
                    original_node_id, node_label = groups
                    node_unique_id = original_node_id
                elif pattern_idx == 2:  # Full format with id
                    original_node_id, node_unique_id, node_label = groups
                else:  # Pattern 3 - complex parsing
                    original_node_id, middle_part, node_label = groups
                    node_unique_id = original_node_id
                
                # Skip if we've already processed this node in this file
                node_key = f"{file_basename}::{original_node_id}"
                if node_key in processed_nodes:
                    continue
                processed_nodes.add(node_key)
                
                # Clean up the label
                clean_label = self.clean_node_label(node_label, file_basename)
                
                # Skip empty or invalid labels
                if not clean_label or clean_label.lower() in ['node', 'graph', 'cluster']:
                    continue
                
                # Enhanced deduplication: check for existing similar nodes
                similar_node_id = self.find_similar_node(clean_label, node_unique_id, file_basename)
                
                if similar_node_id:
                    # Reuse existing similar node
                    simple_node_id = similar_node_id
                    print(f"    Merged duplicate: '{node_label}' -> '{clean_label}' (reusing {simple_node_id})")
                else:
                    # Create new node
                    simple_node_id = f"node-{self.node_counter}"
                    self.label_to_simple[clean_label] = simple_node_id
                    self.simple_to_label[simple_node_id] = clean_label
                    self.file_sources[simple_node_id] = file_basename
                    self.node_counter += 1
                
                # Map original ID to the simple ID (possibly deduplicated)
                full_original_id = f"{file_basename}::{original_node_id}"
                self.original_to_simple[full_original_id] = simple_node_id
                self.original_to_simple[original_node_id] = simple_node_id  # Also map without file prefix
                nodes_found += 1
        
        # Extract edges with multiple patterns for function call graphs
        edge_patterns = [
            # Standard format: Node1 -> Node2
            re.compile(r'(Node\d+)\s*->\s*(Node\d+)(?:\s*\[[^\]]*\])?'),
            # Alternative format: source -> target
            re.compile(r'(\w+)\s*->\s*(\w+)(?:\s*\[[^\]]*\])?'),
        ]
        
        edges_found = 0
        processed_edges = set()
        
        for pattern in edge_patterns:
            for match in pattern.finditer(content):
                source_original, target_original = match.groups()
                
                # Try to find nodes with file prefix first, then without
                source_candidates = [f"{file_basename}::{source_original}", source_original]
                target_candidates = [f"{file_basename}::{target_original}", target_original]
                
                source_simple = None
                target_simple = None
                
                for src_candidate in source_candidates:
                    if src_candidate in self.original_to_simple:
                        source_simple = self.original_to_simple[src_candidate]
                        break
                
                for tgt_candidate in target_candidates:
                    if tgt_candidate in self.original_to_simple:
                        target_simple = self.original_to_simple[tgt_candidate]
                        break
                
                if source_simple and target_simple and source_simple != target_simple:
                    edge = (source_simple, target_simple)
                    # Check both edge directions for global deduplication
                    reverse_edge = (target_simple, source_simple)
                    if edge not in processed_edges and edge not in self.all_edges:
                        self.all_edges.append(edge)
                        processed_edges.add(edge)
                        edges_found += 1
        
        print(f"  Found {nodes_found} nodes, {edges_found} edges")
        if nodes_found == 0:
            print(f"  Note: This appears to be a dependency graph rather than a call graph")
    
    def combine_all_dot_files(self):
        """Find and process all DOT files in the Doxygen output directory"""
        dot_files = self.find_dot_files()
        
        if not dot_files:
            return False
        
        print(f"\nProcessing {len(dot_files)} DOT files...")
        
        for dot_file in dot_files:
            self.process_single_dot_file(dot_file)
        
        print(f"\nCombined results:")
        print(f"Total unique nodes: {len(self.simple_to_label)}")
        print(f"Total unique edges: {len(self.all_edges)}")
        
        # Final deduplication pass to ensure no duplicates remain
        self.final_deduplication_pass()
        
        print(f"After final deduplication:")
        print(f"Final unique nodes: {len(self.simple_to_label)}")
        print(f"Final unique edges: {len(self.all_edges)}")
        
        return len(self.simple_to_label) > 0
    
    def final_deduplication_pass(self):
        """Perform a final pass to remove any remaining duplicates"""
        initial_edges = len(self.all_edges)
        
        # Remove duplicate edges (keep only unique edges)
        unique_edges = []
        seen_edges = set()
        
        for edge in self.all_edges:
            source, target = edge
            
            # Only keep if we haven't seen this edge connection before
            if edge not in seen_edges:
                unique_edges.append(edge)
                seen_edges.add(edge)
        
        removed_edges = initial_edges - len(unique_edges)
        if removed_edges > 0:
            print(f"  Removed {removed_edges} duplicate edges")
        
        self.all_edges = unique_edges
        
        # Clean up orphaned mappings
        valid_node_ids = set(self.simple_to_label.keys())
        
        # Clean original_to_simple mapping
        old_mapping_count = len(self.original_to_simple)
        self.original_to_simple = {
            orig_id: simple_id for orig_id, simple_id in self.original_to_simple.items()
            if simple_id in valid_node_ids
        }
        cleaned_mappings = old_mapping_count - len(self.original_to_simple)
        if cleaned_mappings > 0:
            print(f"  Cleaned {cleaned_mappings} orphaned node mappings")
        
        # Clean file_sources mapping
        self.file_sources = {
            node_id: source for node_id, source in self.file_sources.items()
            if node_id in valid_node_ids
        }
    
    def calculate_hierarchical_layout(self):
        """Calculate positions for nodes in a hierarchical layout with minimal edge crossings and better visual flow"""
        nodes = self.simple_to_label
        edges = self.all_edges
        
        # Build adjacency lists
        incoming = {node: [] for node in nodes}
        outgoing = {node: [] for node in nodes}
        
        for source, target in edges:
            if source in nodes and target in nodes:
                outgoing[source].append(target)
                incoming[target].append(source)
        
        # Identify isolated nodes (not connected to anything)
        isolated_nodes = []
        connected_nodes = {}
        
        for node in nodes:
            if not incoming[node] and not outgoing[node]:
                isolated_nodes.append(node)
            else:
                connected_nodes[node] = nodes[node]
        
        # Enhanced root finding based on program entry points and execution sequence
        roots = [node for node in connected_nodes if not incoming[node]]
        
        if not roots:
            # Look for program entry points with enhanced sequence logic
            entry_candidates = []
            for node in connected_nodes.keys():
                node_label = connected_nodes[node].lower()
                priority = 0
                
                # Main function patterns (highest priority)
                if any(pattern in node_label for pattern in ['main', '__main__', 'main()', 'int main']):
                    priority = 20
                # Initialization and setup functions (second priority)
                elif any(pattern in node_label for pattern in ['__init__', 'constructor', 'setup', 'start', 'begin']):
                    priority = 15
                # Configuration and initialization helpers
                elif any(pattern in node_label for pattern in ['init', 'config', 'configure', 'initialize']):
                    priority = 12
                # Core execution functions
                elif any(pattern in node_label for pattern in ['run', 'execute', 'process', 'loop', 'update']):
                    priority = 10
                # Input/Output and communication functions
                elif any(pattern in node_label for pattern in ['read', 'write', 'send', 'receive', 'input', 'output']):
                    priority = 8
                # Timer and scheduling functions
                elif any(pattern in node_label for pattern in ['timer', 'delay', 'wait', 'sleep', 'schedule']):
                    priority = 6
                # Event handlers and callbacks
                elif any(pattern in node_label for pattern in ['handle', 'callback', 'event', 'interrupt', 'trigger']):
                    priority = 5
                # Error handling and exceptions
                elif any(pattern in node_label for pattern in ['error', 'fail', 'exception', 'abort', 'catch']):
                    priority = 3
                # Test functions (lower priority in main flow)
                elif any(pattern in node_label for pattern in ['test', 'unittest', 'pytest', 'assert', 'check']):
                    priority = 2
                # Everything else
                else:
                    priority = 1
                
                # Boost priority for nodes with many outgoing connections (likely orchestrators)
                connectivity_boost = min(5, len(outgoing[node]))
                priority += connectivity_boost
                
                entry_candidates.append((node, priority))
            
            if entry_candidates:
                # Sort by priority, then by outgoing connections, then by incoming connections
                entry_candidates.sort(key=lambda x: (x[1], len(outgoing[x[0]]), -len(incoming[x[0]])), reverse=True)
                # Select top entry points, but limit to prevent too many roots
                max_roots = min(5, max(1, len(entry_candidates) // 10))
                roots = [node for node, priority in entry_candidates[:max_roots]]
            else:
                # Fall back to nodes with most outgoing connections
                roots = sorted(connected_nodes.keys(), key=lambda x: len(outgoing[x]), reverse=True)[:3]
        
        # Enhanced level assignment with execution sequence awareness
        levels = {}
        visited = set()
        queue = [(root, 0) for root in roots]
        max_level = 0
        
        # First pass: assign basic levels through BFS
        while queue:
            node, level = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            
            if node in levels:
                level = max(level, levels[node])
            levels[node] = level
            max_level = max(max_level, level)
            
            # Enhanced children sorting based on execution sequence patterns
            children = sorted(outgoing[node], key=lambda x: self.get_execution_priority(
                self.simple_to_label[x], len(outgoing[x]), len(incoming[x])
            ), reverse=True)
            
            for child in children:
                if child not in visited and child in connected_nodes:
                    queue.append((child, level + 1))
        
        # Second pass: refine levels based on functional relationships
        self.refine_levels_by_function_type(levels, connected_nodes, incoming, outgoing)
        
        # Update max_level after refinement
        max_level = max(levels.values()) if levels else 0
        
        # Assign remaining connected nodes to appropriate levels
        for node in connected_nodes:
            if node not in levels:
                if incoming[node]:
                    max_parent_level = max(levels.get(parent, 0) for parent in incoming[node])
                    levels[node] = max_parent_level + 1
                    max_level = max(max_level, levels[node])
                else:
                    levels[node] = 0
        
        # Optimize level distribution to reduce crowding
        level_groups = {}
        for node, level in levels.items():
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(node)
        
        # Redistribute overly crowded levels
        max_nodes_per_level = 8  # Adjust this based on your preference
        for level in sorted(level_groups.keys()):
            if len(level_groups[level]) > max_nodes_per_level:
                # Split into sub-levels
                nodes_in_level = level_groups[level]
                # Group by connectivity patterns
                important_nodes = [n for n in nodes_in_level if len(outgoing[n]) > 1 or any(
                    keyword in self.simple_to_label[n].lower() 
                    for keyword in ['main', 'init', 'setup', 'create', 'start']
                )]
                regular_nodes = [n for n in nodes_in_level if n not in important_nodes]
                
                # Keep important nodes at current level
                level_groups[level] = important_nodes
                
                # Move regular nodes to a new intermediate level
                if regular_nodes:
                    new_level = level + 0.5
                    level_groups[new_level] = regular_nodes
                    for node in regular_nodes:
                        levels[node] = new_level
        
        # Calculate positions with improved spacing and dynamic node sizing
        positions = {}
        node_sizes = {}  # Store individual node sizes
        total_nodes = len(nodes)
        
        # Calculate individual node sizes based on content
        max_node_width = 0
        max_node_height = 0
        
        for node_id, label in nodes.items():
            is_isolated = node_id in isolated_nodes
            font_size = self.get_node_font_size(label, is_isolated)
            width, height = self.calculate_node_size(label, font_size, is_isolated)
            node_sizes[node_id] = (width, height)
            max_node_width = max(max_node_width, width)
            max_node_height = max(max_node_height, height)
        
        # Enhanced dynamic spacing based on total node count and maximum node size
        if total_nodes <= 10:
            level_spacing, base_node_spacing = max(220, max_node_height + 150), max(280, max_node_width + 120)
        elif total_nodes <= 30:
            level_spacing, base_node_spacing = max(250, max_node_height + 180), max(320, max_node_width + 140)
        elif total_nodes <= 60:
            level_spacing, base_node_spacing = max(280, max_node_height + 200), max(360, max_node_width + 160)
        else:
            level_spacing, base_node_spacing = max(320, max_node_height + 220), max(400, max_node_width + 180)
        
        # Calculate canvas dimensions with better proportions
        max_nodes_in_level = max(len(level_nodes) for level_nodes in level_groups.values()) if level_groups else 1
        
        # More generous width calculation for better layout with increased gaps
        if total_nodes <= 20:
            main_graph_width = max(1200, max_nodes_in_level * base_node_spacing + 600)
        elif total_nodes <= 50:
            main_graph_width = max(1600, max_nodes_in_level * base_node_spacing + 800)
        else:
            main_graph_width = max(2200, max_nodes_in_level * base_node_spacing + 1000)
        
        # Reserve space for isolated nodes with better proportions and increased spacing
        if isolated_nodes:
            if len(isolated_nodes) <= 5:
                isolated_area_width = 400
            elif len(isolated_nodes) <= 15:
                isolated_area_width = 550
            else:
                isolated_area_width = 700
        else:
            isolated_area_width = 0
            
        canvas_width = main_graph_width + isolated_area_width
        
        # Position connected nodes with improved alignment
        sorted_levels = sorted(level_groups.keys())
        for level in sorted_levels:
            level_nodes = level_groups[level]
            
            # Smart spacing calculation with increased gaps
            if len(level_nodes) > 12:
                node_spacing = max(280, main_graph_width // (len(level_nodes) + 1))
            elif len(level_nodes) > 8:
                node_spacing = max(320, main_graph_width // (len(level_nodes) + 1))
            elif len(level_nodes) > 4:
                node_spacing = max(base_node_spacing + 60, main_graph_width // (len(level_nodes) + 1))
            else:
                node_spacing = base_node_spacing + 80
            
            # Center the nodes in the level with better margins and increased spacing
            total_width = (len(level_nodes) - 1) * node_spacing
            start_x = max(200, (main_graph_width - total_width) // 2)
            
            # Enhanced sorting for better execution sequence within each level
            sorted_level_nodes = sorted(level_nodes, key=lambda x: (
                -self.get_execution_priority(self.simple_to_label[x], len(outgoing[x]), len(incoming[x])),  # Execution priority first
                -len(outgoing[x]),  # Functions that call many others (orchestrators) next
                -len(incoming[x]),  # Popular functions (utilities) after that
                self.get_function_category_order(self.simple_to_label[x]),  # Function type ordering
                self.simple_to_label[x].lower()  # Alphabetical as final tiebreaker
            ))
            
            for i, node in enumerate(sorted_level_nodes):
                x = start_x + i * node_spacing
                y = 200 + level * level_spacing  # Increased top margin and spacing
                positions[node] = (x, y)
        
        # Position isolated nodes with enhanced organization and increased spacing
        if isolated_nodes:
            # Create better visual separation with organized columns and more spacing
            if len(isolated_nodes) <= 6:
                isolated_cols = 1
                gap = 150  # Increased separation
            elif len(isolated_nodes) <= 18:
                isolated_cols = 2
                gap = 180
            else:
                isolated_cols = 3
                gap = 200
            
            isolated_start_x = main_graph_width + gap
            isolated_spacing_x = max_node_width + 60  # Increased horizontal spacing based on max width
            isolated_spacing_y = max_node_height + 50  # Increased vertical spacing based on max height
            
            # Enhanced organization of isolated nodes by execution sequence and type
            def get_isolated_node_priority(node):
                label = self.simple_to_label[node].lower()
                
                # Priority order for isolated functions (higher = earlier in layout)
                if any(keyword in label for keyword in ['main', '__main__', 'init', 'setup']):
                    return (1, label)  # Critical functions first
                elif any(keyword in label for keyword in ['config', 'configure', 'initialize']):
                    return (2, label)  # Configuration functions
                elif any(keyword in label for keyword in ['read', 'input', 'get']):
                    return (3, label)  # Input functions
                elif any(keyword in label for keyword in ['process', 'calculate', 'compute']):
                    return (4, label)  # Processing functions
                elif any(keyword in label for keyword in ['write', 'output', 'send']):
                    return (5, label)  # Output functions
                elif any(keyword in label for keyword in ['validate', 'check', 'verify']):
                    return (6, label)  # Validation functions
                elif any(keyword in label for keyword in ['timer', 'delay', 'wait']):
                    return (7, label)  # Timing functions
                elif any(keyword in label for keyword in ['update', 'modify', 'set']):
                    return (8, label)  # Modification functions
                elif any(keyword in label for keyword in ['save', 'store', 'persist']):
                    return (9, label)  # Storage functions
                elif any(keyword in label for keyword in ['cleanup', 'close', 'finalize']):
                    return (10, label) # Cleanup functions
                elif any(keyword in label for keyword in ['test', 'check', 'assert']):
                    return (11, label) # Test functions
                elif any(keyword in label for keyword in ['error', 'fail', 'exception']):
                    return (12, label) # Error handling
                elif any(keyword in label for keyword in ['helper', 'utility', 'util']):
                    return (13, label) # Utility functions last
                else:
                    return (7, label)  # Default to middle priority
            
            sorted_isolated = sorted(isolated_nodes, key=get_isolated_node_priority)
            
            for i, node in enumerate(sorted_isolated):
                col = i % isolated_cols
                row = i // isolated_cols
                x = isolated_start_x + col * isolated_spacing_x
                y = 200 + row * isolated_spacing_y  # Match main graph start with increased spacing
                positions[node] = (x, y)
        
        return positions, node_sizes, max_node_width, max_node_height, len(isolated_nodes), canvas_width
    
    def calculate_node_size(self, label, font_size=11, is_isolated=False):
        """Calculate optimal node size based on text content and font size"""
        # Base character width estimation (pixels per character)
        char_width_map = {
            9: 5.5,   # Small font
            10: 6.0,
            11: 6.5,  # Default font
            12: 7.0,  # Main function font
            13: 7.5,
            14: 8.0,
            16: 9.0,
        }
        
        char_width = char_width_map.get(font_size, 6.5)
        
        # Calculate text dimensions
        text_width = len(label) * char_width
        
        # Minimum and maximum sizes
        min_width = 100
        max_width = 300
        min_height = 50
        max_height = 100
        
        # Calculate width with padding
        padding_horizontal = 20
        calculated_width = max(min_width, min(max_width, text_width + padding_horizontal))
        
        # Calculate height based on font size and potential line wrapping
        padding_vertical = 20
        line_height = font_size + 4  # Font size plus line spacing
        
        # Check if text needs wrapping
        if text_width > (max_width - padding_horizontal):
            # Multi-line text
            lines_needed = max(1, int(text_width / (max_width - padding_horizontal)) + 1)
            calculated_height = max(min_height, min(max_height, lines_needed * line_height + padding_vertical))
        else:
            # Single line text
            calculated_height = max(min_height, line_height + padding_vertical)
        
        # Adjust for isolated nodes (slightly smaller)
        if is_isolated:
            calculated_width = max(min_width - 10, calculated_width - 10)
            calculated_height = max(min_height - 5, calculated_height - 5)
        
        return int(calculated_width), int(calculated_height)
    
    def get_node_font_size(self, label, is_isolated=False):
        """Get font size based on node type"""
        label_lower = label.lower()
        
        if is_isolated:
            return 10
        elif any(pattern in label_lower for pattern in ['main', '__main__', 'main()', 'int main']):
            return 12  # Main functions get larger font
        elif any(keyword in label_lower for keyword in ['__init__', 'constructor', 'destructor', '~', 'setup', 'start', 'begin', 'run']):
            return 11
        elif any(keyword in label_lower for keyword in ['error', 'fail', 'exception', 'abort', 'throw', 'catch', 'except']):
            return 11
        elif any(keyword in label_lower for keyword in ['test', 'unittest', 'pytest', 'assert', 'check']):
            return 10
        else:
            return 11  # Default font size
    
    def get_node_style(self, label, is_isolated=False, node_width=None, node_height=None):
        """Determine node style based on function type and characteristics with dynamic sizing"""
        label_lower = label.lower()
        font_size = self.get_node_font_size(label, is_isolated)
        
        # Base style components
        base_style = "rounded=1;whiteSpace=wrap;html=1;shadow=1;"
        
        if is_isolated:
            color_style = "fillColor=#f8f9fa;strokeColor=#868e96;strokeWidth=1;dashed=1;fontColor=#495057;"
        elif any(pattern in label_lower for pattern in ['main', '__main__', 'main()', 'int main']):
            color_style = "fillColor=#ff6b6b;strokeColor=#e03131;fontStyle=1;fontColor=white;"
        elif any(keyword in label_lower for keyword in ['__init__', 'constructor', 'destructor', '~', 'setup', 'start', 'begin', 'run']):
            color_style = "fillColor=#51cf66;strokeColor=#37b24d;fontColor=white;"
        elif any(keyword in label_lower for keyword in ['init', 'config', 'configure', 'initialize']):
            color_style = "fillColor=#69db7c;strokeColor=#51cf66;fontColor=white;"
        elif any(keyword in label_lower for keyword in ['error', 'fail', 'exception', 'abort', 'throw', 'catch', 'except']):
            color_style = "fillColor=#ffd43b;strokeColor=#fab005;fontColor=#212529;"
        elif any(keyword in label_lower for keyword in ['test', 'unittest', 'pytest', 'assert', 'check']):
            color_style = "fillColor=#da77f2;strokeColor=#be4bdb;fontColor=white;"
        elif any(keyword in label_lower for keyword in ['read', 'write', 'send', 'receive', 'transmit', 'input', 'output', 'print', 'cout', 'cin']):
            color_style = "fillColor=#9775fa;strokeColor=#7950f2;fontColor=white;"
        elif any(keyword in label_lower for keyword in ['timer', 'delay', 'wait', 'sleep', 'time', 'clock']):
            color_style = "fillColor=#ff8787;strokeColor=#fd7e14;fontColor=white;"
        elif any(keyword in label_lower for keyword in ['get', 'set', 'property', 'getter', 'setter', 'accessor']):
            color_style = "fillColor=#38d9a9;strokeColor=#20c997;fontColor=white;"
        else:
            color_style = "fillColor=#74c0fc;strokeColor=#339af0;fontColor=white;"
        
        font_style = f"fontSize={font_size};"
        
        return base_style + color_style + font_style
        """Determine node style based on function type and characteristics"""
        label_lower = label.lower()
        
        if is_isolated:
            return "rounded=1;whiteSpace=wrap;html=1;fillColor=#f8f9fa;strokeColor=#868e96;strokeWidth=1;dashed=1;fontColor=#495057;shadow=1;fontSize=11;"
        elif any(pattern in label_lower for pattern in ['main', '__main__', 'main()', 'int main']):
            return "rounded=1;whiteSpace=wrap;html=1;fillColor=#ff6b6b;strokeColor=#e03131;fontStyle=1;fontColor=white;shadow=1;fontSize=12;"
        elif any(keyword in label_lower for keyword in ['__init__', 'constructor', 'destructor', '~', 'setup', 'start', 'begin', 'run']):
            return "rounded=1;whiteSpace=wrap;html=1;fillColor=#51cf66;strokeColor=#37b24d;fontColor=white;shadow=1;fontSize=11;"
        elif any(keyword in label_lower for keyword in ['init', 'config', 'configure', 'initialize']):
            return "rounded=1;whiteSpace=wrap;html=1;fillColor=#69db7c;strokeColor=#51cf66;fontColor=white;shadow=1;fontSize=11;"
        elif any(keyword in label_lower for keyword in ['error', 'fail', 'exception', 'abort', 'throw', 'catch', 'except']):
            return "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffd43b;strokeColor=#fab005;fontColor=#212529;shadow=1;fontSize=11;"
        elif any(keyword in label_lower for keyword in ['test', 'unittest', 'pytest', 'assert', 'check']):
            return "rounded=1;whiteSpace=wrap;html=1;fillColor=#da77f2;strokeColor=#be4bdb;fontColor=white;shadow=1;fontSize=11;"
        elif any(keyword in label_lower for keyword in ['read', 'write', 'send', 'receive', 'transmit', 'input', 'output', 'print', 'cout', 'cin']):
            return "rounded=1;whiteSpace=wrap;html=1;fillColor=#9775fa;strokeColor=#7950f2;fontColor=white;shadow=1;fontSize=11;"
        elif any(keyword in label_lower for keyword in ['timer', 'delay', 'wait', 'sleep', 'time', 'clock']):
            return "rounded=1;whiteSpace=wrap;html=1;fillColor=#ff8787;strokeColor=#fd7e14;fontColor=white;shadow=1;fontSize=11;"
        elif any(keyword in label_lower for keyword in ['get', 'set', 'property', 'getter', 'setter', 'accessor']):
            return "rounded=1;whiteSpace=wrap;html=1;fillColor=#38d9a9;strokeColor=#20c997;fontColor=white;shadow=1;fontSize=11;"
        else:
            return "rounded=1;whiteSpace=wrap;html=1;fillColor=#74c0fc;strokeColor=#339af0;fontColor=white;shadow=1;fontSize=11;"
    
    def convert_to_drawio(self):
        """Convert the combined graph to Draw.io XML format"""
        if not self.simple_to_label:
            print("Error: No nodes found to convert")
            return False
        
        # Calculate layout
        node_positions, node_sizes, max_node_width, max_node_height, isolated_count, total_canvas_width = self.calculate_hierarchical_layout()
        
        # Calculate canvas dimensions with better proportions for nice flow charts and increased spacing
        total_levels = len(set(pos[1] for pos in node_positions.values())) if node_positions else 3
        level_spacing = 320 if len(self.simple_to_label) > 30 else 280
        canvas_height = max(1400, 500 + total_levels * level_spacing + isolated_count * 120)
        
        # Create the root mxfile element with enhanced metadata
        mxfile = ET.Element('mxfile', 
                           host="app.diagrams.net", 
                           modified="2025-07-18T00:00:00.000Z", 
                           agent="Doxygen-to-Drawio Converter v2.0", 
                           etag="doxygen-generated-flowchart", 
                           version="24.2.5")
        diagram = ET.SubElement(mxfile, 'diagram', 
                               name="Doxygen Function Flow Chart", 
                               id="doxygen-flow-chart")
        
        # Calculate dynamic values with better proportions and increased spacing
        dx_value = str(max(2000, total_canvas_width // 2))
        dy_value = str(max(1200, canvas_height // 2))
        page_width = str(max(1800, total_canvas_width + 400))
        page_height = str(max(1400, canvas_height + 400))
        
        graph_model = ET.SubElement(diagram, 'mxGraphModel', 
                                   dx=dx_value, dy=dy_value, grid="1", gridSize="10", 
                                   guides="1", tooltips="1", connect="1", 
                                   arrows="1", fold="1", page="1", pageScale="1", 
                                   pageWidth=page_width, pageHeight=page_height, 
                                   math="0", shadow="0")
        
        root = ET.SubElement(graph_model, 'root')
        
        # Add default layers
        ET.SubElement(root, 'mxCell', id="0")
        layer1 = ET.SubElement(root, 'mxCell', id="1")
        layer1.set('parent', '0')
        
        # Add isolated nodes header with enhanced styling and increased spacing
        if isolated_count > 0:
            isolated_area_width = 700 if isolated_count > 15 else 550 if isolated_count > 5 else 400
            main_graph_width = total_canvas_width - isolated_area_width
            
            # Add a decorative background for isolated functions area with increased spacing
            background_cell = ET.SubElement(root, 'mxCell',
                                          id="isolated-background",
                                          value="",
                                          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#f8f9fa;strokeColor=#dee2e6;strokeWidth=1;opacity=30;",
                                          vertex="1")
            background_cell.set('parent', '1')
            
            background_geometry = ET.SubElement(background_cell, 'mxGeometry',
                                              x=str(main_graph_width + 80), y="140",
                                              width=str(isolated_area_width - 80), 
                                              height=str(max(700, isolated_count * 130)))
            background_geometry.set('as', 'geometry')
            
            # Add "Isolated Functions" header with enhanced styling and increased spacing
            header_cell = ET.SubElement(root, 'mxCell',
                                       id="isolated-header",
                                       value="🔧 Isolated Functions",
                                       style="text;html=1;strokeColor=#495057;fillColor=#e9ecef;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=1;fontSize=14;fontStyle=1;fontColor=#495057;strokeWidth=1;shadow=1;",
                                       vertex="1")
            header_cell.set('parent', '1')
            
            header_geometry = ET.SubElement(header_cell, 'mxGeometry',
                                           x=str(main_graph_width + 120), y="150",
                                           width="200", height="35")
            header_geometry.set('as', 'geometry')
            
            # Add a more subtle separator line with increased spacing
            separator_cell = ET.SubElement(root, 'mxCell',
                                         id="separator-line",
                                         value="",
                                         style="rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#adb5bd;strokeWidth=1;dashed=1;opacity=50;",
                                         vertex="1")
            separator_cell.set('parent', '1')
            
            separator_geometry = ET.SubElement(separator_cell, 'mxGeometry',
                                             x=str(main_graph_width + 50), y="120",
                                             width="2", height=str(max(700, isolated_count * 130)))
            separator_geometry.set('as', 'geometry')
        
        # Add nodes with dynamic sizing
        for node_id, label in self.simple_to_label.items():
            x, y = node_positions[node_id]
            node_width, node_height = node_sizes[node_id]
            
            # Escape HTML entities
            safe_label = label.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            # Check if isolated
            is_isolated = node_id not in [s for s, t in self.all_edges] and node_id not in [t for s, t in self.all_edges]
            
            # Get appropriate style with dynamic sizing
            style = self.get_node_style(label, is_isolated, node_width, node_height)
            
            # Create node cell
            node_cell = ET.SubElement(root, 'mxCell', 
                                     id=node_id,
                                     value=safe_label,
                                     style=style,
                                     vertex="1")
            node_cell.set('parent', '1')
            
            # Add geometry with calculated size
            geometry = ET.SubElement(node_cell, 'mxGeometry',
                                   x=str(x), y=str(y),
                                   width=str(node_width), height=str(node_height))
            geometry.set('as', 'geometry')
        
        # Add edges with enhanced styling for better visual flow and collision avoidance
        edge_counter = 1
        for source_id, target_id in self.all_edges:
            if source_id in node_positions and target_id in node_positions:
                edge_id = f"edge-{edge_counter}"
                
                # Get node positions and sizes
                source_x, source_y = node_positions[source_id]
                target_x, target_y = node_positions[target_id]
                source_width, source_height = node_sizes[source_id]
                target_width, target_height = node_sizes[target_id]
                
                # Calculate connection points to avoid overlapping with node content
                # Use bottom center of source and top center of target for downward flow
                if target_y > source_y:  # Downward flow
                    source_connection_x = source_x + source_width // 2
                    source_connection_y = source_y + source_height
                    target_connection_x = target_x + target_width // 2
                    target_connection_y = target_y
                elif target_y < source_y:  # Upward flow
                    source_connection_x = source_x + source_width // 2
                    source_connection_y = source_y
                    target_connection_x = target_x + target_width // 2
                    target_connection_y = target_y + target_height
                else:  # Same level - use side connections
                    if target_x > source_x:  # Right-ward
                        source_connection_x = source_x + source_width
                        source_connection_y = source_y + source_height // 2
                        target_connection_x = target_x
                        target_connection_y = target_y + target_height // 2
                    else:  # Left-ward
                        source_connection_x = source_x
                        source_connection_y = source_y + source_height // 2
                        target_connection_x = target_x + target_width
                        target_connection_y = target_y + target_height // 2
                
                # Get function labels for styling decisions
                source_label = self.simple_to_label[source_id].lower()
                target_label = self.simple_to_label[target_id].lower()
                
                # Enhanced edge styling based on execution sequence and function relationships
                style = self.get_edge_style(source_label, target_label, source_connection_x, source_connection_y, 
                                          target_connection_x, target_connection_y)
                
                # Create edge cell
                edge_cell = ET.SubElement(root, 'mxCell',
                                        id=edge_id,
                                        style=style,
                                        edge="1",
                                        source=source_id,
                                        target=target_id)
                edge_cell.set('parent', '1')
                
                # Add geometry with enhanced waypoints for execution flow
                geometry = ET.SubElement(edge_cell, 'mxGeometry', relative="1")
                geometry.set('as', 'geometry')
                
                # Add intelligent waypoints based on execution sequence patterns
                self.add_execution_waypoints(geometry, source_connection_x, source_connection_y, 
                                           target_connection_x, target_connection_y, 
                                           source_label, target_label, max_node_width)
                
                edge_counter += 1
        
        # Convert to formatted XML and write to file
        rough_string = ET.tostring(mxfile, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")
        
        # Clean up formatting
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        pretty_xml = '\n'.join(lines)
        
        # Write to file
        try:
            with open(self.output_file, 'w', encoding='utf-8') as file:
                file.write(pretty_xml)
            return True
        except IOError as e:
            print(f"Error writing to {self.output_file}: {e}")
            return False
    
    def convert(self):
        """Main conversion function with integrated Doxygen support"""
        print(Colors.colored("Doxygen to Draw.io Converter with Integrated Doxygen", Colors.BLUE))
        print(Colors.colored("=" * 55, Colors.BLUE))
        
        # Step 1: Setup Doxygen if requested
        if self.run_doxygen:
            if not self.setup_doxygen():
                print(Colors.colored("❌ Doxygen setup failed. Cannot proceed.", Colors.RED))
                return False
        
        # Step 2: Check if Doxygen output directory exists
        if not os.path.isdir(self.doxygen_output_dir):
            print(Colors.colored(f"Error: Doxygen output directory '{self.doxygen_output_dir}' does not exist.", Colors.RED))
            
            if not self.run_doxygen:
                print(Colors.colored("\n💡 Suggestion: Use --run-doxygen to automatically generate documentation", Colors.CYAN))
                print("Or make sure to:")
                print("1. Run Doxygen on your project first")
                print("2. Set HAVE_DOT=YES in your Doxyfile")
                print("3. Set CALL_GRAPH=YES in your Doxyfile")
                print("4. Set CALLER_GRAPH=YES in your Doxyfile (optional)")
            
            return False
        
        # Step 3: Combine all DOT files
        if not self.combine_all_dot_files():
            print(Colors.colored("Error: No valid nodes found in DOT files", Colors.RED))
            
            if not self.run_doxygen:
                print(Colors.colored("\n💡 Try running with --run-doxygen to regenerate documentation", Colors.CYAN))
            
            return False
        
        # Step 4: Convert to Draw.io format
        print(Colors.colored(f"\nConverting to Draw.io format...", Colors.YELLOW))
        if not self.convert_to_drawio():
            return False
        
        print(Colors.colored(f"\n✅ Draw.io file generated: {self.output_file}", Colors.GREEN))
        print(Colors.colored(f"📊 Total nodes: {len(self.simple_to_label)}, Total edges: {len(self.all_edges)}", Colors.CYAN))
        
        if hasattr(self, 'file_sources'):
            source_files = set(self.file_sources.values())
            print(Colors.colored(f"📁 Combined from {len(source_files)} DOT files", Colors.CYAN))
        
        # Step 5: Auto-open or prompt to open
        if self.auto_open:
            self.open_drawio_file()
        elif not self.no_prompt:
            if self.prompt_to_open():
                self.open_drawio_file()
            else:
                print(Colors.colored(f"\n🌐 To open manually:", Colors.YELLOW))
                print("1. Go to app.diagrams.net (draw.io)")
                print("2. Click 'Open Existing Diagram'")
                print(f"3. Select the file: {os.path.abspath(self.output_file)}")
        else:
            print(Colors.colored(f"\n📁 File saved: {os.path.abspath(self.output_file)}", Colors.CYAN))
        
        return True

    def open_drawio_file(self):
        """Open the generated Draw.io file directly in the browser or app"""
        if not os.path.exists(self.output_file):
            print(Colors.colored("Error: Draw.io file not found!", Colors.RED))
            return False
        
        abs_file_path = os.path.abspath(self.output_file)
        system = sys.platform.lower()
        
        try:
            # Try to open with draw.io desktop app first (preferred method)
            desktop_app_opened = False
            
            if system == "darwin":  # macOS
                try:
                    subprocess.run(["open", "-a", "draw.io", abs_file_path], check=True, capture_output=True)
                    print(Colors.colored(f"📱 Opened with draw.io desktop app", Colors.GREEN))
                    desktop_app_opened = True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # draw.io desktop app not found, continue to try other methods
                    pass
                    
            elif system.startswith("linux"):  # Linux
                try:
                    subprocess.run(["drawio", abs_file_path], check=True, capture_output=True)
                    print(Colors.colored(f"📱 Opened with draw.io desktop app", Colors.GREEN))
                    desktop_app_opened = True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # draw.io desktop app not found, continue to try other methods
                    pass
                    
            elif system.startswith("win"):  # Windows
                try:
                    subprocess.run(["draw.io.exe", abs_file_path], check=True, capture_output=True)
                    print(Colors.colored(f"� Opened with draw.io desktop app", Colors.GREEN))
                    desktop_app_opened = True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # draw.io desktop app not found, continue to try other methods
                    pass
            
            # If desktop app didn't work, try default application
            if not desktop_app_opened:
                try:
                    if system == "darwin":  # macOS
                        subprocess.run(["open", abs_file_path], check=True)
                        print(Colors.colored(f"� Opened with default application", Colors.GREEN))
                    elif system.startswith("linux"):  # Linux
                        subprocess.run(["xdg-open", abs_file_path], check=True)
                        print(Colors.colored(f"📁 Opened with default application", Colors.GREEN))
                    elif system.startswith("win"):  # Windows
                        subprocess.run(["start", abs_file_path], shell=True, check=True)
                        print(Colors.colored(f"� Opened with default application", Colors.GREEN))
                    desktop_app_opened = True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # Even default app failed
                    pass
            
            # Only open web browser if local methods failed
            if not desktop_app_opened:
                print(Colors.colored(f"🌐 Opening draw.io web app (desktop app not available)...", Colors.YELLOW))
                drawio_url = "https://app.diagrams.net/"
                webbrowser.open(drawio_url)
                print(Colors.colored(f"💡 To load your file in the web app:", Colors.CYAN))
                print(f"   1. Click 'Open Existing Diagram'")
                print(f"   2. Select: {abs_file_path}")
            else:
                print(Colors.colored(f"💡 If the file doesn't open correctly:", Colors.CYAN))
                print(f"   File location: {abs_file_path}")
                print(f"   You can also open it manually at: https://app.diagrams.net")
            
            return True
            
        except Exception as e:
            print(Colors.colored(f"Warning: Could not auto-open file: {e}", Colors.YELLOW))
            print(Colors.colored(f"📁 File location: {abs_file_path}", Colors.CYAN))
            print(Colors.colored(f"🌐 Manual option: Go to https://app.diagrams.net and open the file", Colors.CYAN))
            return False
    
    def prompt_to_open(self):
        """Prompt user to open the file"""
        try:
            response = input(Colors.colored("Would you like to open the diagram now? (y/n): ", Colors.YELLOW)).lower().strip()
            return response in ['y', 'yes', '1', 'true']
        except (KeyboardInterrupt, EOFError):
            print()  # New line after interrupt
            return False

def main():
    parser = argparse.ArgumentParser(
        description='Convert Doxygen DOT output to Draw.io format with integrated Doxygen support',
        epilog='''
Examples:
  # Convert existing Doxygen output
  python3 doxygenToDrawio.py -d doxygen_output/html

  # Automatically run Doxygen and convert (recommended)
  python3 doxygenToDrawio.py --run-doxygen --source-dir ./src --auto-open

  # Create flowchart from current directory
  python3 doxygenToDrawio.py --run-doxygen --auto-open

  # Convert C++ project with custom Doxygen output location
  python3 doxygenToDrawio.py --run-doxygen -s ./src --doxygen-html ./docs/html -o my_project_flowchart.drawio

  # Specify custom DOT path for call graphs
  python3 doxygenToDrawio.py --run-doxygen --dot-path /usr/local/bin/dot --auto-open

  # Run without call graphs (when DOT is not available)
  python3 doxygenToDrawio.py --run-doxygen --no-prompt
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Existing arguments
    parser.add_argument('-d', '--doxygen-dir', default='doxygen_output/html',
                       help='Doxygen output directory (default: doxygen_output/html)')
    parser.add_argument('-o', '--output', default='doxygen_callgraph.drawio',
                       help='Output Draw.io file (default: doxygen_callgraph.drawio)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    parser.add_argument('--auto-open', action='store_true',
                       help='Automatically open the generated Draw.io file')
    parser.add_argument('--no-prompt', action='store_true',
                       help='Skip the prompt to open the file')
    
    # New Doxygen integration arguments
    parser.add_argument('--run-doxygen', action='store_true',
                       help='Automatically run Doxygen before converting (recommended)')
    parser.add_argument('-s', '--source-dir', default='.',
                       help='Source code directory for Doxygen analysis (default: current directory)')
    parser.add_argument('--doxygen-html', default='doxygen_output/html',
                       help='Doxygen HTML output directory (default: doxygen_output/html)')
    parser.add_argument('--dot-path', 
                       help='Path to DOT executable (e.g., /usr/local/bin/dot). Required for call graphs.')
    parser.add_argument('--find-dot', action='store_true',
                       help='Search for DOT executable on system and exit')
    
    args = parser.parse_args()
    
    # Handle find-dot command
    if args.find_dot:
        print(Colors.colored("🔍 Searching for DOT executable...", Colors.BLUE))
        converter = DoxygenToDrawioConverter()
        dot_path = converter.check_dot_available()
        if dot_path:
            print(Colors.colored(f"\n✅ DOT found at: {dot_path}", Colors.GREEN))
            print(f"Use this with: --dot-path {dot_path}")
        else:
            print(Colors.colored(f"\n❌ DOT not found on this system", Colors.RED))
        return 0
    
    # Validate arguments
    if args.run_doxygen and not os.path.exists(args.source_dir):
        print(f"Error: Source directory '{args.source_dir}' does not exist.")
        return 1
    
    # Validate DOT path if provided
    if args.dot_path and not os.path.exists(args.dot_path):
        print(f"Error: DOT executable not found at '{args.dot_path}'")
        return 1
    
    # Create converter instance with new parameters
    # Use --doxygen-html when running Doxygen, otherwise use -d/--doxygen-dir
    doxygen_output_dir = args.doxygen_html if args.run_doxygen else args.doxygen_dir
    
    converter = DoxygenToDrawioConverter(
        doxygen_output_dir=doxygen_output_dir,
        output_file=args.output,
        auto_open=args.auto_open,
        no_prompt=args.no_prompt,
        source_dir=os.path.abspath(args.source_dir),
        run_doxygen=args.run_doxygen,
        dot_path=args.dot_path
    )
    
    # Show configuration
    if args.verbose or args.run_doxygen:
        print(Colors.colored("Configuration:", Colors.CYAN))
        print(f"  Source directory: {converter.source_dir}")
        print(f"  Doxygen output: {converter.doxygen_output_dir}")
        print(f"  Output file: {converter.output_file}")
        print(f"  Run Doxygen: {converter.run_doxygen}")
        print(f"  Auto-open: {converter.auto_open}")
        print("")
    
    # Perform conversion
    success = converter.convert()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
