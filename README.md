# 🎬 Claude Studio Producer

> Budget-aware multi-agent video production orchestration using Claude Agent SDK

A production-grade AI system that manages competitive video production pilots, evaluates quality, and reallocates budgets dynamically.

## 🌟 Features

- **🎯 Producer Agent**: Analyzes requests and budgets, creates multi-tier pilot strategies
- **🎨 Multi-Tier Production**: Static images, motion graphics, animation, photorealistic video
- **🏃 Parallel Competitive Pilots**: Test multiple approaches simultaneously, continue the best
- **🔍 Critic Agent**: Gap analysis and quality-based budget reallocation
- **💰 Budget-Aware**: Real-time cost tracking with automatic budget enforcement
- **📊 Quality Feedback Loops**: Automated evaluation at every stage

## 🎥 How It Works

Claude Studio Producer orchestrates AI agents to create professional videos:
```
1. Producer → Analyzes request & budget, creates 2-3 competitive pilot strategies
2. Pilots   → Generate test scenes in parallel (different quality tiers)
3. Critic   → Evaluates results, cancels poor pilots, reallocates budget
4. Winners  → Complete full production with allocated budget
5. Editor   → Selects best final video
```

## 💵 Cost Models (2025 Pricing)

| Tier | Cost/Second | Use Case | Quality Ceiling |
|------|-------------|----------|-----------------|
| Static Images | $0.04 | Slideshows, presentations | 75/100 |
| Motion Graphics | $0.15 | Explainers, product demos | 85/100 |
| Animated | $0.25 | Storytelling, characters | 90/100 |
| Photorealistic | $0.50 | High-end commercials | 95/100 |

## 📦 Installation

### Prerequisites

- Python 3.9+
- Anthropic API key ([get one here](https://console.anthropic.com/))

### Quick Install (Recommended)

```bash
# Install directly from GitHub
pip install git+https://github.com/aaronmarkham/claude-studio-producer.git

# Or install in editable mode for development
git clone https://github.com/aaronmarkham/claude-studio-producer.git
cd claude-studio-producer
pip install -e .
```

### Manual Setup

```bash
# Clone the repository
git clone https://github.com/aaronmarkham/claude-studio-producer.git
cd claude-studio-producer

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (Git Bash):
source .venv/Scripts/activate
# On macOS/Linux:
source .venv/bin/activate

# Install the package
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

## ⚡ Quick Start
```python
import asyncio
from core import StudioOrchestrator

async def main():
    # Create orchestrator
    orchestrator = StudioOrchestrator(num_variations=3)
    
    # Run production
    result = await orchestrator.produce_video(
        user_request="""
        Create a 60-second video: 'A day in the life of a developer
        using AI tools'. Show: standup, coding, debugging, deploying.
        """,
        total_budget=150.00
    )
    
    print(f"Status: {result.status}")
    print(f"Best pilot: {result.best_pilot.pilot_id}")
    print(f"Cost: ${result.budget_used:.2f}")

asyncio.run(main())
```

Or use the included example:
```bash
python examples/full_production.py
```

## 🏗️ Architecture
```
core/
├── orchestrator.py     # Main pipeline coordinator
├── producer.py         # Budget planning & pilot strategies
├── critic.py          # Quality evaluation & budget decisions
├── budget.py          # Cost models & tracking
└── claude_client.py   # Claude SDK abstraction

agents/                # Specialized agent implementations
skills/                # Agent skills for progressive disclosure
examples/              # Usage examples
```

## 📚 Examples

### Test Individual Agents
```bash
# Test Producer
python examples/test_producer.py

# Test Critic
python examples/test_critic.py

# Full production pipeline
python examples/full_production.py
```

### Cost Estimation
```bash
# Estimate costs for different tiers
python scripts/estimate_costs.py
```

## 🔧 Configuration

Edit `.env`:
```bash
# Required
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Optional
DEFAULT_BUDGET=100.00
DEFAULT_VARIATIONS=3
```

## 🎯 Use Cases

- **Product Demos**: Automated demo video generation
- **Educational Content**: Tutorial and explainer videos
- **Marketing**: Social media content at scale
- **Documentation**: Visual documentation generation
- **Prototyping**: Rapid video concept testing

## 🤝 Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📋 Roadmap

- [x] Core Producer/Critic agents
- [x] Budget-aware orchestration
- [x] Multi-tier cost models
- [x] Script Writer agent
- [x] Video Generator agent (with mock mode)
- [x] Video QA agent with vision analysis (mock mode)
- [x] Skills system (video-generation, scene-analysis)
- [ ] Real video API integration (Runway, Pika)
- [ ] Editor agent with EDL generation
- [ ] Web UI dashboard
- [ ] Prompt library & templates
- [ ] Performance benchmarks

## 📄 License

MIT-0 (MIT No Attribution) - see [LICENSE](LICENSE) for details

This project is released under the most permissive open source license. Use it freely without attribution requirements.

## 🙏 Acknowledgments

- Built on [Claude Agent SDK](https://docs.anthropic.com/agent-sdk)
- Inspired by real production workflows
- Cost models based on 2025 AI video generation pricing

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/aaronmarkham/claude-studio-producer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/aaronmarkham/claude-studio-producer/discussions)

---

**Note**: This is a framework for orchestrating AI video production. Actual video generation requires API keys for services like Runway, Pika Labs, or similar providers.
