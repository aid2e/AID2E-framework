"""Tests for DAG types and validation."""

import pytest
from aid2e.utilities.workflows import (
    DagDefinition,
    DagNode,
    DagEdge,
    DagNodeType,
    topological_sort,
    detect_cycles,
    DagValidator,
)


@pytest.fixture
def simple_2step_dag():
    """Create a simple 2-stage DAG: evaluate -> aggregate."""
    return DagDefinition(
        name="dtlz2_eval",
        nodes=[
            DagNode(node_id="evaluate", node_type=DagNodeType.STAGE),
            DagNode(node_id="aggregate", node_type=DagNodeType.STAGE, depends_on=["evaluate"]),
        ],
    )


@pytest.fixture
def linear_3step_dag():
    """Create a linear 3-stage DAG: prepare -> evaluate -> aggregate."""
    return DagDefinition(
        name="linear_workflow",
        nodes=[
            DagNode(node_id="prepare", node_type=DagNodeType.STAGE),
            DagNode(node_id="evaluate", node_type=DagNodeType.STAGE, depends_on=["prepare"]),
            DagNode(node_id="aggregate", node_type=DagNodeType.STAGE, depends_on=["evaluate"]),
        ],
    )


@pytest.fixture
def multi_source_dag():
    """Create DAG with multiple source nodes and convergence."""
    return DagDefinition(
        name="convergence_workflow",
        nodes=[
            DagNode(node_id="prepare_a", node_type=DagNodeType.STAGE),
            DagNode(node_id="prepare_b", node_type=DagNodeType.STAGE),
            DagNode(node_id="merge", node_type=DagNodeType.STAGE, depends_on=["prepare_a", "prepare_b"]),
        ],
    )


@pytest.fixture
def cyclic_dag():
    """Create a DAG with a cycle: A -> B -> C -> A."""
    return DagDefinition(
        name="cyclic",
        nodes=[
            DagNode(node_id="A", node_type=DagNodeType.STAGE, depends_on=["C"]),
            DagNode(node_id="B", node_type=DagNodeType.STAGE, depends_on=["A"]),
            DagNode(node_id="C", node_type=DagNodeType.STAGE, depends_on=["B"]),
        ],
    )


class TestDagEdgeInference:
    """Test automatic edge inference from depends_on."""
    
    def test_edges_inferred_from_depends_on(self, simple_2step_dag):
        """Edges should be inferred from node depends_on lists."""
        assert len(simple_2step_dag.edges) == 1
        edge = simple_2step_dag.edges[0]
        assert edge.src_id == "evaluate"
        assert edge.dst_id == "aggregate"
    
    def test_multiple_dependencies(self, multi_source_dag):
        """Multiple dependencies should create multiple edges."""
        assert len(multi_source_dag.edges) == 2
        dst_ids = {edge.dst_id for edge in multi_source_dag.edges}
        assert dst_ids == {"merge"}
        src_ids = {edge.src_id for edge in multi_source_dag.edges}
        assert src_ids == {"prepare_a", "prepare_b"}


class TestTopologicalSort:
    """Test topological sorting."""
    
    def test_simple_2step_sort(self, simple_2step_dag):
        """Simple 2-step should sort correctly."""
        order = topological_sort(simple_2step_dag)
        assert order.sorted_node_ids == ["evaluate", "aggregate"]
    
    def test_linear_3step_sort(self, linear_3step_dag):
        """Linear 3-step should maintain order."""
        order = topological_sort(linear_3step_dag)
        assert order.sorted_node_ids == ["prepare", "evaluate", "aggregate"]
    
    def test_multi_source_sort(self, multi_source_dag):
        """Sources can appear in any order; merge comes last."""
        order = topological_sort(multi_source_dag)
        assert order.sorted_node_ids[-1] == "merge"
        assert set(order.sorted_node_ids[:2]) == {"prepare_a", "prepare_b"}
    
    def test_execution_layers(self, multi_source_dag):
        """Execution layers should group parallelizable nodes."""
        order = topological_sort(multi_source_dag)
        assert len(order.layers) == 2
        # First layer has both sources (parallelizable)
        assert len(order.layers[0]) == 2
        # Second layer has merge (dependent on both sources)
        assert len(order.layers[1]) == 1
        assert order.layers[1][0].node_id == "merge"
    
    def test_cyclic_dag_raises(self, cyclic_dag):
        """Sorting a cyclic DAG should raise ValueError."""
        with pytest.raises(ValueError, match="contains a cycle"):
            topological_sort(cyclic_dag)


class TestCycleDetection:
    """Test cycle detection."""
    
    def test_no_cycle_simple(self, simple_2step_dag):
        """Simple DAG has no cycle."""
        result = detect_cycles(simple_2step_dag)
        assert not result.has_cycle
    
    def test_no_cycle_linear(self, linear_3step_dag):
        """Linear DAG has no cycle."""
        result = detect_cycles(linear_3step_dag)
        assert not result.has_cycle
    
    def test_detects_simple_cycle(self, cyclic_dag):
        """Should detect 3-node cycle."""
        result = detect_cycles(cyclic_dag)
        assert result.has_cycle
        assert result.cycle_nodes is not None
        assert len(result.cycle_nodes) >= 2
    
    def test_cycle_details(self, cyclic_dag):
        """Cycle details should be correct."""
        result = detect_cycles(cyclic_dag)
        assert result.cycle_edges is not None
        # All cycle edges should form a path
        edges = result.cycle_edges
        for i in range(len(edges) - 1):
            assert edges[i][1] == edges[i + 1][0]


class TestDagValidator:
    """Test comprehensive DAG validation."""
    
    def test_validate_valid_dag(self, simple_2step_dag):
        """Valid DAG should have no errors."""
        errors = DagValidator.validate(simple_2step_dag)
        assert errors == []
    
    def test_detect_cycle_in_validation(self, cyclic_dag):
        """Validation should detect cycles."""
        errors = DagValidator.validate(cyclic_dag)
        assert len(errors) > 0
        assert any("cycle" in err.lower() for err in errors)
    
    def test_self_dependency_error(self):
        """Self-dependency should be caught."""
        dag = DagDefinition(
            name="invalid",
            nodes=[
                DagNode(node_id="A", node_type=DagNodeType.STAGE, depends_on=["A"]),
            ],
        )
        errors = DagValidator.validate(dag)
        assert any("self-dependency" in err.lower() for err in errors)
    
    def test_unknown_dependency_error(self):
        """Reference to unknown node should be caught."""
        dag = DagDefinition(
            name="invalid",
            nodes=[
                DagNode(node_id="A", node_type=DagNodeType.STAGE, depends_on=["unknown"]),
            ],
        )
        errors = DagValidator.validate(dag)
        assert any("unknown" in err.lower() for err in errors)
    
    def test_no_source_nodes_error(self):
        """DAG with no source nodes should be caught."""
        dag = DagDefinition(
            name="invalid",
            edges=[
                DagEdge(src_id="A", dst_id="B"),
                DagEdge(src_id="B", dst_id="A"),
            ],
            nodes=[
                DagNode(node_id="A", node_type=DagNodeType.STAGE),
                DagNode(node_id="B", node_type=DagNodeType.STAGE),
            ],
        )
        errors = DagValidator.validate(dag)
        assert any("source" in err.lower() for err in errors)
    
    def test_validate_and_sort(self, simple_2step_dag):
        """validate_and_sort should return order and empty errors for valid DAG."""
        order, errors = DagValidator.validate_and_sort(simple_2step_dag)
        assert errors == []
        assert order is not None
        assert order.sorted_node_ids == ["evaluate", "aggregate"]
    
    def test_validate_and_sort_with_errors(self, cyclic_dag):
        """validate_and_sort should return errors for invalid DAG."""
        order, errors = DagValidator.validate_and_sort(cyclic_dag)
        assert order is None
        assert len(errors) > 0


class TestDagNodeTypes:
    """Test different node types."""
    
    def test_stage_nodes(self):
        """DAG can have STAGE nodes."""
        dag = DagDefinition(
            name="stages",
            nodes=[
                DagNode(node_id="s1", node_type=DagNodeType.STAGE),
                DagNode(node_id="s2", node_type=DagNodeType.STAGE, depends_on=["s1"]),
            ],
        )
        assert all(node.node_type == DagNodeType.STAGE for node in dag.nodes)
    
    def test_job_nodes(self):
        """DAG can have JOB nodes."""
        dag = DagDefinition(
            name="jobs",
            nodes=[
                DagNode(node_id="j1", node_type=DagNodeType.JOB),
                DagNode(node_id="j2", node_type=DagNodeType.JOB, depends_on=["j1"]),
            ],
        )
        assert all(node.node_type == DagNodeType.JOB for node in dag.nodes)
    
    def test_mixed_node_types(self):
        """DAG can have mixed STAGE and JOB nodes."""
        dag = DagDefinition(
            name="mixed",
            nodes=[
                DagNode(node_id="stage1", node_type=DagNodeType.STAGE),
                DagNode(node_id="job1", node_type=DagNodeType.JOB, depends_on=["stage1"]),
            ],
        )
        node_types = {node.node_type for node in dag.nodes}
        assert len(node_types) == 2


class TestLargeDAG:
    """Test with larger DAGs."""
    
    def test_diamond_dag(self):
        """Diamond shape: A -> B,C -> D."""
        dag = DagDefinition(
            name="diamond",
            nodes=[
                DagNode(node_id="A", node_type=DagNodeType.STAGE),
                DagNode(node_id="B", node_type=DagNodeType.STAGE, depends_on=["A"]),
                DagNode(node_id="C", node_type=DagNodeType.STAGE, depends_on=["A"]),
                DagNode(node_id="D", node_type=DagNodeType.STAGE, depends_on=["B", "C"]),
            ],
        )
        errors = DagValidator.validate(dag)
        assert errors == []
        
        order = topological_sort(dag)
        assert order.sorted_node_ids[0] == "A"
        assert set(order.sorted_node_ids[1:3]) == {"B", "C"}
        assert order.sorted_node_ids[3] == "D"
    
    def test_wide_dag(self):
        """Wide DAG: single source feeds 5 tasks."""
        nodes = [DagNode(node_id="source", node_type=DagNodeType.STAGE)]
        nodes.extend([
            DagNode(node_id=f"task{i}", node_type=DagNodeType.STAGE, depends_on=["source"])
            for i in range(1, 6)
        ])
        
        dag = DagDefinition(name="wide", nodes=nodes)
        errors = DagValidator.validate(dag)
        assert errors == []
        
        order = topological_sort(dag)
        assert order.sorted_node_ids[0] == "source"
        assert set(order.sorted_node_ids[1:]) == {f"task{i}" for i in range(1, 6)}
        
        # All tasks should be in same layer (parallelizable)
        assert len(order.layers) == 2
        assert len(order.layers[1]) == 5
