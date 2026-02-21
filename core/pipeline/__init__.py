"""Pipeline modules — extracted from produce_video.py for maintainability."""

from core.pipeline.display import (
    print_header, print_budget_tiers, print_scene_table,
    print_asset_summary, print_full_scene_list,
)
from core.pipeline.figures import (
    _match_scene_to_figure, distribute_figures_to_scenes, load_kb_figures,
)
from core.pipeline.audio import generate_scene_audio
from core.pipeline.assets import generate_mock_assets, generate_live_assets
from core.pipeline.video_stages import (
    load_training_trial, script_segments_to_aligned,
    reconstruct_aligned_segments,
)
