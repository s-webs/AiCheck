"""Generate analytical charts for PDF reports."""

import io
import logging
from typing import Dict, List

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

logger = logging.getLogger(__name__)

# Try to set up Cyrillic font support
try:
    # Try to find a Cyrillic-capable font
    cyrillic_fonts = [
        'DejaVu Sans',
        'Arial',
        'Liberation Sans',
        'Times New Roman',
    ]
    cyrillic_font = None
    for font_name in cyrillic_fonts:
        try:
            font_path = fm.findfont(fm.FontProperties(family=font_name))
            if font_path:
                cyrillic_font = font_name
                break
        except Exception:
            continue
    
    if cyrillic_font:
        plt.rcParams['font.family'] = cyrillic_font
        logger.debug("Using font: %s", cyrillic_font)
    else:
        plt.rcParams['font.family'] = 'sans-serif'
        logger.warning("No Cyrillic font found, charts may show replacement characters")
except Exception as e:
    logger.warning("Failed to configure Cyrillic font: %s", e)
    plt.rcParams['font.family'] = 'sans-serif'


def create_quality_scores_chart(quality_scores: Dict[str, float]) -> bytes:
    """
    Create a bar chart showing all quality scores (0-10 scale).
    
    Args:
        quality_scores: Dictionary with quality metric names and scores
        
    Returns:
        PNG image as bytes
    """
    # Russian labels for metrics
    labels_map = {
        "clarity": "Ясность формулировок",
        "single_best_answer": "Один лучший ответ",
        "distractors": "Качество дистракторов",
        "no_clues": "Отсутствие подсказок",
        "language": "Языковая корректность",
        "structure_consistency": "Структурная согласованность",
        "difficulty_balance": "Баланс сложности",
        "content_accuracy": "Точность содержания",
        "formatting_quality": "Качество форматирования",
        "answer_key_quality": "Качество ключа ответов",
    }
    
    # Prepare data
    metric_names = []
    scores = []
    colors = []
    
    for key, label in labels_map.items():
        score = quality_scores.get(key)
        if score is not None:
            metric_names.append(label)
            scores.append(float(score))
            # Color coding: green for high (8-10), yellow for medium (5-7.9), red for low (0-4.9)
            if score >= 8:
                colors.append('#2ecc71')  # Green
            elif score >= 5:
                colors.append('#f39c12')  # Orange/Yellow
            else:
                colors.append('#e74c3c')  # Red
    
    if not scores:
        logger.warning("No quality scores to plot")
        # Create empty chart
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 'Нет данных для отображения', 
                ha='center', va='center', transform=ax.transAxes)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
    else:
        # Create bar chart
        fig, ax = plt.subplots(figsize=(12, 6))
        bars = ax.bar(range(len(metric_names)), scores, color=colors, edgecolor='black', linewidth=0.5)
        
        # Add value labels on bars
        for i, (bar, score) in enumerate(zip(bars, scores)):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.2,
                   f'{score:.1f}', ha='center', va='bottom', fontsize=9)
        
        # Customize chart
        ax.set_xlabel('Метрики качества', fontsize=11, fontweight='bold')
        ax.set_ylabel('Оценка (0-10)', fontsize=11, fontweight='bold')
        ax.set_title('Оценки качества тестовых заданий', fontsize=13, fontweight='bold', pad=15)
        ax.set_xticks(range(len(metric_names)))
        ax.set_xticklabels(metric_names, rotation=45, ha='right', fontsize=9)
        ax.set_ylim(0, 10.5)
        ax.set_yticks(range(0, 11, 2))
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        
        # Add horizontal reference lines
        ax.axhline(y=8, color='green', linestyle='--', alpha=0.3, linewidth=1)
        ax.axhline(y=5, color='orange', linestyle='--', alpha=0.3, linewidth=1)
    
    plt.tight_layout()
    
    # Save to bytes
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    
    return buf.read()


def create_risk_distribution_chart(risk_level: str, major_findings: List[Dict]) -> bytes:
    """
    Create a pie chart showing distribution of findings by severity level.
    
    Args:
        risk_level: Overall risk level (LOW, MEDIUM, HIGH)
        major_findings: List of findings with 'severity' field
        
    Returns:
        PNG image as bytes
    """
    # Count findings by severity
    severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for finding in major_findings:
        severity = finding.get("severity", "").upper()
        if severity in severity_counts:
            severity_counts[severity] += 1
    
    # Prepare data
    labels = []
    sizes = []
    colors_pie = []
    explode = []
    
    severity_labels_ru = {
        "HIGH": "Высокий",
        "MEDIUM": "Средний",
        "LOW": "Низкий",
    }
    
    for severity in ["HIGH", "MEDIUM", "LOW"]:
        count = severity_counts[severity]
        if count > 0:
            labels.append(f"{severity_labels_ru[severity]}\n({count})")
            sizes.append(count)
            if severity == "HIGH":
                colors_pie.append('#e74c3c')  # Red
                explode.append(0.1)
            elif severity == "MEDIUM":
                colors_pie.append('#f39c12')  # Orange
                explode.append(0.05)
            else:
                colors_pie.append('#2ecc71')  # Green
                explode.append(0)
    
    if not sizes:
        # Create empty chart
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, 'Нет данных для отображения', 
                ha='center', va='center', transform=ax.transAxes)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
    else:
        # Create pie chart
        fig, ax = plt.subplots(figsize=(8, 6))
        
        wedges, texts, autotexts = ax.pie(
            sizes, 
            labels=labels, 
            colors=colors_pie,
            explode=explode if len(explode) == len(sizes) else [0] * len(sizes),
            autopct='%1.1f%%',
            startangle=90,
            textprops={'fontsize': 10, 'fontweight': 'bold'}
        )
        
        # Customize percentage text
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(11)
        
        # Add overall risk level to title
        risk_level_ru = {"HIGH": "Высокий", "MEDIUM": "Средний", "LOW": "Низкий"}.get(risk_level.upper(), risk_level)
        ax.set_title(f'Распределение выводов по уровню риска\n(Общий уровень риска: {risk_level_ru})', 
                    fontsize=12, fontweight='bold', pad=15)
    
    plt.tight_layout()
    
    # Save to bytes
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    
    return buf.read()
