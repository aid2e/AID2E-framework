"""DAG (Directed Acyclic Graph) types and validation for workflow execution.

This module defines the core DAG structures used to represent workflow stages
and their dependencies. It provides topological sorting and cycle detection
to ensure workflows are executable.

Inspired by multi-step execution patterns, the DAG supports:
- Explicit stage dependencies (depends_on list)
- Topological ordering for correct execution sequence
- Cycle detection to prevent invalid workflows
- Comprehensive validation with detailed error reporting

Key concepts:
    DagNode: A stage or job in the workflow DAG
    DagEdge: A directed dependency edge between two nodes
    DagDefinition: Complete DAG with nodes and edges
    TopologicalOrder: Result of topological sort with validation
    DagValidator: Helper for comprehensive DAG validation

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from typing import List, Dict, Set, Optional, Union, Tuple
from collections import defaultdict, deque
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class DagNodeType(str, Enum):
    """Type of node in the DAG."""
    STAGE = "stage"
    JOB = "job"


class DagEdge(BaseModel):
    """A directed edge in the DAG representing a dependency.
    
    An edge from source to destination indicates that the source node
    must complete before the destination node can begin execution.
    
    Attributes:
        src_id: Unique identifier of the source node.
        dst_id: Unique identifier of the destination node.
        edge_type: Type of dependency (results, datasets, etc).
    """
    src_id: str = Field(..., description="Source node ID")
    dst_id: str = Field(..., description="Destination node ID")
    edge_type: str = Field(default="results", description="Dependency type (results, datasets, etc)")


class DagNode(BaseModel):
    """A node in the workflow DAG.
    
    Can represent either a Stage (logical execution unit) or a Job (smallest
    schedulable unit). Each node has a unique ID and optional dependencies.
    
    Attributes:
        node_id: Unique identifier for the node.
        node_type: Type of node (STAGE or JOB).
        depends_on: List of upstream node IDs this node depends on.
        description: Optional human-readable description.
    """
    node_id: str = Field(..., description="Unique node identifier")
    node_type: DagNodeType = Field(..., description="Type of node (STAGE or JOB)")
    depends_on: List[str] = Field(default_factory=list, description="Upstream node dependencies")
    description: Optional[str] = Field(default=None, description="Node description")


class DagDefinition(BaseModel):
    """Complete DAG definition with nodes and edges.
    
    Represents the structure of a workflow as a directed acyclic graph.
    Can be constructed either from explicit edges or inferred from node
    depends_on lists.
    
    Attributes:
        name: Name of the DAG.
        nodes: List of all nodes in the DAG.
        edges: Optional explicit edge list (can be inferred from depends_on).
    """
    name: str = Field(..., description="DAG name")
    nodes: List[DagNode] = Field(..., min_items=1, description="DAG nodes")
    edges: List[DagEdge] = Field(default_factory=list, description="Explicit edges (optional)")
    
    @model_validator(mode="after")
    def build_edges_from_depends_on(self) -> "DagDefinition":
        """Build edge list from node depends_on lists if not explicitly provided.
        
        If edges are not provided, infer them from each node's depends_on list.
        This allows simpler YAML/config specification.
        """
        if not self.edges:
            inferred_edges: List[DagEdge] = []
            for node in self.nodes:
                for dep_id in node.depends_on:
                    inferred_edges.append(DagEdge(src_id=dep_id, dst_id=node.node_id))
            self.edges = inferred_edges
        return self
    
    def get_node_by_id(self, node_id: str) -> Optional[DagNode]:
        """Get a node by its ID."""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None
    
    def get_node_ids(self) -> Set[str]:
        """Get all node IDs in the DAG."""
        return {node.node_id for node in self.nodes}


class TopologicalOrder(BaseModel):
    """Result of topological sort with validation metadata.
    
    Contains the sorted node list and metadata about the sorting process.
    
    Attributes:
        sorted_nodes: Nodes in topological order (ready to execute left-to-right).
        sorted_node_ids: Just the IDs in topological order.
        layers: Nodes grouped by execution layer (all nodes in layer N can run in parallel).
    """
    sorted_nodes: List[DagNode]
    sorted_node_ids: List[str]
    layers: List[List[DagNode]]
    
    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True


class CycleDetectionResult(BaseModel):
    """Result of cycle detection.
    
    Attributes:
        has_cycle: Whether a cycle was detected.
        cycle_nodes: If cycle found, the nodes forming the cycle.
        cycle_edges: If cycle found, the edges in the cycle.
    """
    has_cycle: bool
    cycle_nodes: Optional[List[str]] = None
    cycle_edges: Optional[List[Tuple[str, str]]] = None


def topological_sort(dag: DagDefinition) -> TopologicalOrder:
    """Perform topological sort on the DAG using Kahn's algorithm.
    
    Returns nodes in an order such that for every edge (u, v), u comes
    before v in the ordering. Suitable for execution in sequence or layers.
    
    Uses Kahn's algorithm (BFS-based):
    1. Compute in-degree for each node
    2. Queue all nodes with in-degree 0
    3. Dequeue and process; decrement neighbors' in-degrees
    4. Enqueue neighbors with in-degree 0
    
    Args:
        dag: The DAG to sort.
        
    Returns:
        TopologicalOrder with sorted nodes, IDs, and execution layers.
        
    Raises:
        ValueError: If DAG contains a cycle (detected during sort).
        
    Example:
        >>> dag = DagDefinition(name="workflow", nodes=[...], edges=[...])
        >>> order = topological_sort(dag)
        >>> for node_id in order.sorted_node_ids:
        ...     print(f"Execute: {node_id}")
    """
    node_ids = dag.get_node_ids()
    node_map = {node.node_id: node for node in dag.nodes}
    
    # Build adjacency list and compute in-degrees
    graph: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = defaultdict(int)
    
    for node_id in node_ids:
        in_degree[node_id] = 0
    
    for edge in dag.edges:
        graph[edge.src_id].append(edge.dst_id)
        in_degree[edge.dst_id] += 1
    
    # Kahn's algorithm
    queue = deque([node_id for node_id in node_ids if in_degree[node_id] == 0])
    sorted_ids: List[str] = []
    
    while queue:
        node_id = queue.popleft()
        sorted_ids.append(node_id)
        
        for neighbor in graph[node_id]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    if len(sorted_ids) != len(node_ids):
        raise ValueError(
            f"DAG contains a cycle. Only {len(sorted_ids)}/{len(node_ids)} "
            "nodes were sorted. Check dependencies for loops."
        )
    
    sorted_nodes = [node_map[node_id] for node_id in sorted_ids]
    
    # Group into execution layers (nodes that can run in parallel)
    layers = _compute_execution_layers(dag, sorted_ids, node_map)
    
    return TopologicalOrder(
        sorted_nodes=sorted_nodes,
        sorted_node_ids=sorted_ids,
        layers=layers,
    )


def _compute_execution_layers(
    dag: DagDefinition,
    sorted_ids: List[str],
    node_map: Dict[str, DagNode],
) -> List[List[DagNode]]:
    """Compute execution layers: nodes that can run in parallel.
    
    Each layer contains nodes with no dependencies (or all dependencies met
    in previous layers). This enables visualization and potential parallelism.
    
    Args:
        dag: The DAG.
        sorted_ids: Topologically sorted node IDs.
        node_map: Map of node_id to DagNode.
        
    Returns:
        List of layers, each containing nodes that can execute in parallel.
    """
    layers: List[List[DagNode]] = []
    processed: Set[str] = set()
    
    while len(processed) < len(sorted_ids):
        layer: List[DagNode] = []
        layer_ids: Set[str] = set()
        
        for node_id in sorted_ids:
            if node_id in processed or node_id in layer_ids:
                continue
            
            node = node_map[node_id]
            deps_ready = all(dep_id in processed for dep_id in node.depends_on)
            
            if deps_ready:
                layer.append(node)
                layer_ids.add(node_id)
        
        if layer:
            for node_id in layer_ids:
                processed.add(node_id)
            layers.append(layer)
        else:
            break
    
    return layers


def detect_cycles(dag: DagDefinition) -> CycleDetectionResult:
    """Detect cycles in the DAG using DFS.
    
    Uses depth-first search with color marking:
    - White (0): not visited
    - Gray (1): currently visiting (in recursion stack)
    - Black (2): fully visited
    
    If we encounter a gray node, a back edge (cycle) is found.
    
    Args:
        dag: The DAG to check.
        
    Returns:
        CycleDetectionResult with has_cycle flag and cycle details if found.
        
    Example:
        >>> dag = DagDefinition(name="workflow", nodes=[...], edges=[...])
        >>> result = detect_cycles(dag)
        >>> if result.has_cycle:
        ...     print(f"Cycle found: {result.cycle_nodes}")
    """
    node_ids = dag.get_node_ids()
    
    # Build adjacency list
    graph: Dict[str, List[str]] = defaultdict(list)
    for edge in dag.edges:
        graph[edge.src_id].append(edge.dst_id)
    
    # Color states: 0=white, 1=gray, 2=black
    colors: Dict[str, int] = {node_id: 0 for node_id in node_ids}
    parent: Dict[str, Optional[str]] = {node_id: None for node_id in node_ids}
    
    def dfs(node_id: str, path: List[str]) -> Optional[List[str]]:
        """DFS visit. Returns cycle path if found."""
        colors[node_id] = 1  # Gray
        path.append(node_id)
        
        for neighbor in graph[node_id]:
            if colors[neighbor] == 1:
                # Back edge found; cycle exists from neighbor to node_id
                cycle_start = path.index(neighbor)
                return path[cycle_start:] + [neighbor]
            elif colors[neighbor] == 0:
                result = dfs(neighbor, path)
                if result:
                    return result
        
        path.pop()
        colors[node_id] = 2  # Black
        return None
    
    for node_id in node_ids:
        if colors[node_id] == 0:
            cycle = dfs(node_id, [])
            if cycle:
                cycle_nodes = cycle[:-1]  # Remove duplicate end node
                cycle_edges = [(cycle[i], cycle[i + 1]) for i in range(len(cycle) - 1)]
                return CycleDetectionResult(
                    has_cycle=True,
                    cycle_nodes=cycle_nodes,
                    cycle_edges=cycle_edges,
                )
    
    return CycleDetectionResult(has_cycle=False)


class DagValidator:
    """Comprehensive DAG validator.
    
    Validates DAG structure, node references, and execution feasibility.
    """
    
    @staticmethod
    def validate(dag: DagDefinition) -> List[str]:
        """Validate DAG and return list of errors (empty if valid).
        
        Checks:
        - No cycles
        - All dependencies reference existing nodes
        - No self-dependencies
        - At least one node with in-degree 0 (source nodes)
        
        Args:
            dag: The DAG to validate.
            
        Returns:
            List of error messages (empty if valid).
            
        Example:
            >>> errors = DagValidator.validate(dag)
            >>> if errors:
            ...     for err in errors:
            ...         print(f"  - {err}")
        """
        errors: List[str] = []
        node_ids = dag.get_node_ids()
        
        # Check for cycles
        cycle_result = detect_cycles(dag)
        if cycle_result.has_cycle:
            errors.append(
                f"Cycle detected: {' -> '.join(cycle_result.cycle_nodes)} "
                f"-> {cycle_result.cycle_nodes[0]}"
            )
        
        # Check for self-dependencies
        for node in dag.nodes:
            if node.node_id in node.depends_on:
                errors.append(f"Node '{node.node_id}' has self-dependency")
        
        # Check that all dependencies exist
        for node in dag.nodes:
            for dep_id in node.depends_on:
                if dep_id not in node_ids:
                    errors.append(
                        f"Node '{node.node_id}' depends on unknown node '{dep_id}'"
                    )
        
        # Check for source nodes (in-degree 0)
        in_degree: Dict[str, int] = defaultdict(int)
        for edge in dag.edges:
            in_degree[edge.dst_id] += 1
        
        source_nodes = [nid for nid in node_ids if in_degree[nid] == 0]
        if not source_nodes:
            errors.append("No source nodes found (all nodes have incoming edges)")
        
        return errors
    
    @staticmethod
    def validate_and_sort(dag: DagDefinition) -> Tuple[TopologicalOrder, List[str]]:
        """Validate DAG and perform topological sort.
        
        Args:
            dag: The DAG to validate and sort.
            
        Returns:
            Tuple of (TopologicalOrder, errors). If errors non-empty, sort result is invalid.
        """
        errors = DagValidator.validate(dag)
        
        if errors:
            return None, errors
        
        try:
            order = topological_sort(dag)
            return order, []
        except ValueError as e:
            return None, [str(e)]
