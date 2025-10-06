import math


def discounted_cumulative_gain(relevance_scores):
    if not relevance_scores:
        return 0.0

    dcg = 0.0
    for i, relevance in enumerate(relevance_scores):
        dcg += relevance / math.log2(i + 1 + 1)
    return dcg


def ideal_discounted_cumulative_gain(relevance_scores):
    sorted_relevance = sorted(relevance_scores, reverse=True)
    return discounted_cumulative_gain(sorted_relevance)


def normalized_discounted_cumulative_gain(relevance_scores):
    dcg = discounted_cumulative_gain(relevance_scores)
    idcg = ideal_discounted_cumulative_gain(relevance_scores)

    if idcg == 0:
        return 0.0

    return dcg / idcg


if __name__ == "__main__":
    relevance_scores_example = [3, 2, 3, 0, 1, 2]

    dcg_value = discounted_cumulative_gain(relevance_scores_example)
    idcg_value = ideal_discounted_cumulative_gain(relevance_scores_example)
    ndcg_value = normalized_discounted_cumulative_gain(relevance_scores_example)

    print(f"Relevance Scores: {relevance_scores_example}")
    print(f"DCG: {dcg_value:.4f}")
    print(f"IDCG: {idcg_value:.4f}")
    print(f"NDCG: {ndcg_value:.4f}")

    # Another example
    relevance_scores_example_2 = [5, 4, 3, 2, 1]
    dcg_value_2 = discounted_cumulative_gain(relevance_scores_example_2)
    idcg_value_2 = ideal_discounted_cumulative_gain(relevance_scores_example_2)
    ndcg_value_2 = normalized_discounted_cumulative_gain(relevance_scores_example_2)

    print(f"\nRelevance Scores: {relevance_scores_example_2}")
    print(f"DCG: {dcg_value_2:.4f}")
    print(f"IDCG: {idcg_value_2:.4f}")
    print(f"NDCG: {ndcg_value_2:.4f}")

    # Example with all zeros
    relevance_scores_zeros = [0, 0, 0, 0, 0]
    ndcg_value_zeros = normalized_discounted_cumulative_gain(relevance_scores_zeros)
    print(f"\nRelevance Scores: {relevance_scores_zeros}")
    print(f"NDCG: {ndcg_value_zeros:.4f}")
