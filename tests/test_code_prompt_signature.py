"""Tests for code_prompt_signature module."""

import dspy
import pytest

from lw_coder.dspy.code_prompt_signature import CodePromptSignature


def test_code_prompt_signature_definition() -> None:
    """Test that CodePromptSignature is properly defined."""
    # Check signature has required input and output fields
    assert hasattr(CodePromptSignature, "__annotations__")
    annotations = CodePromptSignature.__annotations__

    # Input field
    assert "plan_text" in annotations

    # Output fields
    assert "main_prompt" in annotations
    assert "review_prompt" in annotations
    assert "alignment_prompt" in annotations


def test_code_prompt_signature_docstring() -> None:
    """Test that signature has comprehensive docstring instructions."""
    docstring = CodePromptSignature.__doc__
    assert docstring is not None
    assert len(docstring) > 100  # Should be comprehensive

    # Check for key instructions
    assert "main prompt" in docstring.lower() or "main_prompt" in docstring.lower()
    assert "review" in docstring.lower()
    assert "alignment" in docstring.lower()
    assert "parallel" in docstring.lower()
    assert "test" in docstring.lower()
    assert "mock" in docstring.lower() or "mocking" in docstring.lower()


def test_code_prompt_signature_dspy_compatibility() -> None:
    """Test that CodePromptSignature can be used with DSPy Predict module."""
    # This verifies that DSPy can actually instantiate and use the signature
    # without requiring an actual LLM call
    predictor = dspy.Predict(CodePromptSignature)

    # Verify the predictor was created successfully
    assert predictor is not None
    assert predictor.signature == CodePromptSignature

    # Verify the signature has the expected fields
    signature_instance = predictor.signature
    input_fields = signature_instance.input_fields
    output_fields = signature_instance.output_fields

    # Check input field exists
    assert "plan_text" in input_fields

    # Check all three output fields exist
    assert "main_prompt" in output_fields
    assert "review_prompt" in output_fields
    assert "alignment_prompt" in output_fields
