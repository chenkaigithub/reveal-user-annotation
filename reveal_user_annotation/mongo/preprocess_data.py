__author__ = 'Georgios Rizos (georgerizos@iti.gr)'

import numpy as np
import scipy.sparse as sparse
import networkx as nx
import networkx.algorithms.components as nxalgcom

from reveal_user_annotation.text.clean_text import clean_document, combine_word_list


def get_user_to_bag_of_words_dictionary(user_twitter_id_list, database):
    """
    Returns a python dictionary that maps Twitter user ids to a bag-of-words.

    Inputs: - user_twitter_id_list: A python list of Twitter user ids.
            - database: A Mongo database object.

    Output: - user_to_bag_of_words_dictionary: A python dictionary that maps Twitter user ids to a bag-of-words.
    """
    user_to_bag_of_words_dictionary = dict()
    for user_twitter_id, bag_of_words in read_bag_of_words_for_each_user(user_twitter_id_list, database):
        user_to_bag_of_words_dictionary[user_twitter_id] = bag_of_words

    return user_to_bag_of_words_dictionary


def read_bag_of_words_for_each_user(user_twitter_id_list, database):
    """
    For each Twitter user ids, it reads the corresponding preprocessed bag-of-words.

    Inputs:  - user_twitter_id_list: A python list of Twitter user ids.
             - database: A Mongo database object.

    Outputs: - user_twitter_id: A Twitter user id.
             - bag_of_words: A python dictionary that maps keywords to multiplicity.
    """
    for user_twitter_id in user_twitter_id_list:
        collection_name = str(user_twitter_id)
        user_keywords_collection = database[collection_name]

        user_keywords_cursor = user_keywords_collection.find()
        bag_of_words = next(user_keywords_cursor)

        yield user_twitter_id, bag_of_words


def store_user_documents(user_document_gen, client, mongo_database_name):
    """
    Stores Twitter list objects that a Twitter user is a member of in different mongo collections.

    Inputs: - user_document_gen: A python generator that yields a Twitter user id and an associated document list.
            - client: A pymongo MongoClient object.
            - mongo_database_name: The name of a Mongo database as a string.
    """
    mongo_database = client[mongo_database_name]

    # Iterate over all users to be annotated and store the Twitter lists in mongo.
    for user_twitter_id, user_document_list in user_document_gen:
        collection_name = str(user_twitter_id)
        collection = mongo_database[collection_name]

        for twitter_list in user_document_list:
            collection.insert(twitter_list)


def read_user_documents_for_single_user_generator(user_twitter_id, mongo_database):
    """
    Stores Twitter list objects that a Twitter user is a member of in different mongo collections.

    Inputs: - user_twitter_id: A Twitter user id.
            - mongo_database: A mongo database.

    Yields: - user_twitter_id: A Twitter user id.
            - twitter_lists_list: A python list containing Twitter lists in dictionary (json) format.
    """
    collection_name = str(user_twitter_id)
    collection = mongo_database[collection_name]
    cursor = collection.find()

    for twitter_list in cursor:
        yield twitter_list


def read_user_documents_generator(user_twitter_id_list, client, mongo_database_name):
    """
    Stores Twitter list objects that a Twitter user is a member of in different mongo collections.

    Inputs: - user_twitter_id_list: A python list of Twitter user ids.
            - client: A pymongo MongoClient object.
            - mongo_database_name: The name of a Mongo database as a string.

    Yields: - user_twitter_id: A Twitter user id.
            - twitter_list_gen: A python generator that yields Twitter lists in dictionary (json) format.
    """
    mongo_database = client[mongo_database_name]
    for user_twitter_id in user_twitter_id_list:
        twitter_list_gen = read_user_documents_for_single_user_generator(user_twitter_id, mongo_database)

        yield user_twitter_id, twitter_list_gen


def get_collection_documents_generator(client, database_name, collection_name):
    """
    This is a python generator that yields tweets stored in a mongodb collection.

    Inputs: - client: A pymongo MongoClient object.
            - database_name: The name of a Mongo database as a string.
            - collection_name: The name of the tweet collection as a string.

    Yields: - document: A document in python dictionary (json) format.
    """
    mongo_database = client[database_name]
    collection = mongo_database[collection_name]
    cursor = collection.find()

    for document in cursor:
        yield document


def extract_graphs_and_lemmas_from_tweets(tweet_generator):
    """
    Given a tweet python generator, we encode the information into mention and retweet graphs and a lemma matrix.

    We assume that the tweets are given in increasing timestamp.

    Inputs:  - tweet_generator: A python generator of tweets in python dictionary (json) format.

    Outputs: - mention_graph: The mention graph as a SciPy sparse matrix.
             - retweet_graph: The retweet graph as a SciPy sparse matrix.
             - user_lemma_matrix: The user lemma vector representation matrix as a SciPy sparse matrix.
             - tweet_id_set: A python set containing the Twitter ids for all the dataset tweets.
             - user_id_set: A python set containing the Twitter ids for all the dataset users.
             - lemma_to_attribute: A map from lemmas to numbers in python dictionary format.
    """
    ####################################################################################################################
    # Prepare for iterating over tweets.
    ####################################################################################################################
    # These are initialized as lists for incremental extension.
    tweet_id_set = list()
    user_id_set = list()

    append_tweet_id = tweet_id_set.append
    append_user_id = user_id_set.append

    # Initialize sparse matrix arrays
    mention_graph_row = list()
    mention_graph_col = list()

    retweet_graph_row = list()
    retweet_graph_col = list()

    user_lemma_matrix_row = list()
    user_lemma_matrix_col = list()
    user_lemma_matrix_data = list()

    append_mention_graph_row = mention_graph_row.append
    append_mention_graph_col = mention_graph_col.append

    append_retweet_graph_row = retweet_graph_row.append
    append_retweet_graph_col = retweet_graph_col.append

    append_user_lemma_matrix_row = user_lemma_matrix_row.append
    append_user_lemma_matrix_col = user_lemma_matrix_col.append
    append_user_lemma_matrix_data = user_lemma_matrix_data.append

    # Initialize dictionaries
    id_to_name = dict()
    lemma_to_attribute = dict()

    ####################################################################################################################
    # Iterate over tweets.
    ####################################################################################################################
    for tweet in tweet_generator:
        append_tweet_id(tweet["id"])
        user_id = tweet["user"]["id"]
        id_to_name[user_id] = tweet["user"]["screen_name"]
        append_user_id(user_id)

        # Check if it is a retweet.
        if "retweeted_status" in tweet.keys():
            # We are dealing with a retweet.
            original_tweet = tweet["retweeted_status"]

            tweet_id_set = set(tweet_id_set)

            if original_tweet["id"] not in tweet_id_set:
                # This is the first time we deal with this tweet.
                tweet_id_set = list(tweet_id_set)
                append_tweet_id = tweet_id_set.append
                append_tweet_id(original_tweet["id"])

                original_tweet_user_id = original_tweet["user"]["id"]
                id_to_name[original_tweet_user_id] = original_tweet["user"]["screen_name"]
                append_user_id(original_tweet_user_id)

                append_retweet_graph_row(user_id)
                append_retweet_graph_col(original_tweet_user_id)

                # Extract lemmas from the text.
                tweet_lemmas = clean_document(original_tweet["text"])
                bag_of_lemmas = combine_word_list(tweet_lemmas)
                for lemma, multiplicity in bag_of_lemmas.values():
                    vocabulary_size = len(lemma_to_attribute)
                    attribute = lemma_to_attribute.setdefault(lemma, default=vocabulary_size)

                    append_user_lemma_matrix_row(original_tweet_user_id)
                    append_user_lemma_matrix_col(attribute)
                    append_user_lemma_matrix_data(multiplicity)

                # Check if this tweet was in reply to another user.
                in_reply_to_user_id = original_tweet["in_reply_to_user_id"]
                if in_reply_to_user_id is not None:
                    id_to_name[in_reply_to_user_id] = original_tweet["in_reply_to_user_screen_name"]
                    append_user_id(in_reply_to_user_id)

                    append_mention_graph_row(original_tweet_user_id)
                    append_mention_graph_col(in_reply_to_user_id)

                # Check if this tweet has mentions to other users.
                for user_mention in original_tweet["entities"]["user_mentions"]:
                    mentioned_user_id = user_mention["id"]
                    id_to_name[mentioned_user_id] = user_mention["screen_name"]
                    append_user_id(mentioned_user_id)

                    append_mention_graph_row(original_tweet_user_id)
                    append_mention_graph_col(mentioned_user_id)
            else:
                tweet_id_set = list(tweet_id_set)
                append_tweet_id = tweet_id_set.append

        else:
            # We are dealing with an original tweet.
            #  Extract lemmas from the text.
            tweet_lemmas = clean_document(tweet["text"])
            bag_of_lemmas = combine_word_list(tweet_lemmas)
            for lemma, multiplicity in bag_of_lemmas.values():
                vocabulary_size = len(lemma_to_attribute)
                attribute = lemma_to_attribute.setdefault(lemma, default=vocabulary_size)

                append_user_lemma_matrix_row(user_id)
                append_user_lemma_matrix_col(attribute)
                append_user_lemma_matrix_data(multiplicity)

            # Check if this tweet was in reply to another user.
            in_reply_to_user_id = tweet["in_reply_to_user_id"]
            if in_reply_to_user_id is not None:
                id_to_name[in_reply_to_user_id] = tweet["in_reply_to_user_screen_name"]
                append_user_id(in_reply_to_user_id)

                append_mention_graph_row(user_id)
                append_mention_graph_col(in_reply_to_user_id)

            # Check if this tweet has mentions to other users.
            for user_mention in tweet["entities"]["user_mentions"]:
                mentioned_user_id = user_mention["id"]
                id_to_name[mentioned_user_id] = user_mention["screen_name"]
                append_user_id(mentioned_user_id)

                append_mention_graph_row(user_id)
                append_mention_graph_col(mentioned_user_id)

    ####################################################################################################################
    # Final steps of preprocessing tweets.
    ####################################################################################################################
    # Discard any duplicates.
    tweet_id_set = set(tweet_id_set)
    user_id_set = set(user_id_set)
    number_of_users = len(user_id_set)

    # Form mention graph adjacency matrix.
    mention_graph_row = np.array(mention_graph_row, dtype=np.int64)
    mention_graph_col = np.array(mention_graph_col, dtype=np.int64)
    mention_graph_data = np.ones_like(mention_graph_row, dtype=np.float64)

    mention_graph = sparse.coo_matrix((mention_graph_data, (mention_graph_row, mention_graph_col)),
                                      shape=(number_of_users, number_of_users))

    # Form retweet graph adjacency matrix.
    retweet_graph_row = np.array(retweet_graph_row, dtype=np.int64)
    retweet_graph_col = np.array(retweet_graph_col, dtype=np.int64)
    retweet_graph_data = np.ones_like(retweet_graph_row, dtype=np.float64)

    retweet_graph = sparse.coo_matrix((retweet_graph_data, (retweet_graph_row, retweet_graph_col)),
                                      shape=(number_of_users, number_of_users))

    # Form user-lemma matrix.
    number_of_lemmas = len(lemma_to_attribute)

    user_lemma_matrix_row = np.array(user_lemma_matrix_row, dtype=np.int64)
    user_lemma_matrix_col = np.array(user_lemma_matrix_col, dtype=np.int64)
    user_lemma_matrix_data = np.array(user_lemma_matrix_data, dtype=np.float64)

    user_lemma_matrix = sparse.coo_matrix((user_lemma_matrix_data, (user_lemma_matrix_row, user_lemma_matrix_col)),
                                          shape=(number_of_users, number_of_lemmas))

    return mention_graph, retweet_graph, user_lemma_matrix, tweet_id_set, user_id_set, lemma_to_attribute


def extract_connected_components(graph, connectivity_type="weak"):
    """
    Extract the largest connected component from a graph.

    Inputs:  - graph: An adjacency matrix in scipy sparse matrix format.
             - connectivity_type: A string that can be either: "strong" or "weak".

    Outputs: - largest_connected_component: An adjacency matrix in scipy sparse matrix format.
             - node_to_id: A map from graph node id to Twitter id, in python dictionary format.
    """
    graph = nx.from_scipy_sparse_matrix(graph, create_using=nx.DiGraph())

    if connectivity_type == "weak":
        largest_connected_component_list = nxalgcom.weakly_connected_component_subgraphs()
    elif connectivity_type == "strong":
        largest_connected_component_list = nxalgcom.strongly_connected_component_subgraphs()
    else:
        print("Invalid connectivity type input.")
        raise RuntimeError

    ids = largest_connected_component_list[0].nodes()
    node_to_id = dict(zip(np.arange(len(ids)), ids))
    largest_connected_component = graph[ids, ids]

    return largest_connected_component, node_to_id