import warnings
warnings.filterwarnings('ignore')

import re
import numpy as np
import pandas as pd
from heapq import nsmallest
from nltk.corpus import stopwords
from sklearn.cluster import KMeans
from nltk.tokenize import word_tokenize
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

df = pd.read_csv('Dataset/20k_data.csv',
                 usecols=['Title', 'University Name', 'Link', 'Details'])

# Drop null values
df = df.dropna()
df = df.reset_index(drop=True)

def Clean(text):
    # Convert to lowercase
    text = text.lower()

    # Remove all characters which are not alphabetical or numerical
    text = re.sub(r'[\W_]', ' ', text)

    # Tokenization
    text = word_tokenize(text)

    # Filter out stop words
    text = [w for w in text if not w in set(stopwords.words('english'))]

    return text

def word_embeddings():
    embeddings = {}
    with open("glove.6B.50d.txt", 'r', encoding="utf-8") as f:
        for line in f:
            values = line.split()
            word = values[0]
            vector = np.asarray(values[1:], "float32")
            embeddings[word] = vector
    return embeddings

def Vectorize(text, embeddings):
    # Generate vector representation
    vec = np.zeros(50)
    count = 0
    for i in text:
        try:
            vec += embeddings[i]
            count += 1
        except:
            pass
    return vec/count

centroids = np.load('cluster_centers.npy', allow_pickle=True)

def recommend(text, embeddings, centroids, n):
    temp = Clean(text)
    temp = Vectorize(temp, embeddings)
    diff = centroids - temp
    dist = list(np.sum(diff**2, axis=-1) ** 0.5)
    idx = [i for i in map(dist.index, nsmallest(n, dist))]

    return idx

embeddings = word_embeddings()
result = recommend( my_personal_statement ,embeddings, centroids,)
idx = np.unique(result)

for i in range(len(idx)):
    print('University:', df['University Name'][idx[i]])
    print('Scholarship:', df['Title'][idx[i]])
    print('Link to scholarship:', df['Link'][idx[i]], end='\n\n')