"""Unit tests for budget tracking"""

import pytest
from core.budget import BudgetTracker, ProductionTier, COST_MODELS


def test_budget_initialization():
    """Test budget tracker initialization"""
    tracker = BudgetTracker(total_budget=100.0)

    assert tracker.total_budget == 100.0
    assert tracker.get_remaining_budget() == 100.0
    assert tracker.get_total_spent() == 0.0


def test_record_spend():
    """Test recording spend reduces budget"""
    tracker = BudgetTracker(total_budget=100.0)

    tracker.record_spend("pilot_a", 30.0)

    assert tracker.get_remaining_budget() == 70.0
    assert tracker.get_total_spent() == 30.0


def test_multiple_pilots_tracking():
    """Test tracking multiple pilot spends"""
    tracker = BudgetTracker(total_budget=100.0)

    tracker.record_spend("pilot_a", 30.0)
    tracker.record_spend("pilot_b", 25.0)
    tracker.record_spend("pilot_a", 10.0)  # Additional spend

    assert tracker.get_remaining_budget() == 35.0
    assert tracker.get_total_spent() == 65.0


def test_cannot_overspend():
    """Test that spending more than budget doesn't go negative"""
    tracker = BudgetTracker(total_budget=50.0)

    tracker.record_spend("pilot_a", 60.0)

    # Should still track the spend
    assert tracker.get_total_spent() == 60.0
    # Remaining should be negative (over budget)
    assert tracker.get_remaining_budget() == -10.0


def test_cost_models_exist():
    """Test that all production tiers have cost models"""
    assert ProductionTier.STATIC_IMAGES in COST_MODELS
    assert ProductionTier.MOTION_GRAPHICS in COST_MODELS
    assert ProductionTier.ANIMATED in COST_MODELS
    assert ProductionTier.PHOTOREALISTIC in COST_MODELS


def test_cost_models_pricing():
    """Test that cost models have expected price ordering"""
    static_cost = COST_MODELS[ProductionTier.STATIC_IMAGES].cost_per_second
    motion_cost = COST_MODELS[ProductionTier.MOTION_GRAPHICS].cost_per_second
    animated_cost = COST_MODELS[ProductionTier.ANIMATED].cost_per_second
    photo_cost = COST_MODELS[ProductionTier.PHOTOREALISTIC].cost_per_second

    # Higher tiers should cost more
    assert static_cost < motion_cost < animated_cost < photo_cost


def test_cost_models_quality_ceiling():
    """Test that higher tiers have higher quality ceilings"""
    static_quality = COST_MODELS[ProductionTier.STATIC_IMAGES].quality_ceiling
    motion_quality = COST_MODELS[ProductionTier.MOTION_GRAPHICS].quality_ceiling
    animated_quality = COST_MODELS[ProductionTier.ANIMATED].quality_ceiling
    photo_quality = COST_MODELS[ProductionTier.PHOTOREALISTIC].quality_ceiling

    # Higher tiers should have higher quality ceilings
    assert static_quality < motion_quality < animated_quality < photo_quality
