import json
import re
import os

import pandas as pd
from gensim.models import Word2Vec
from tensorflow.keras.preprocessing.text import Tokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
from gensim.models import Word2Vec
import numpy as np
import pickle

import matplotlib.pyplot as plt
import seaborn as sns
# from keras.preprocessing.text import Tokenizer
# from keras.preprocessing.sequence import pad_sequences
import PreProcessTools

duration_stat = {}
count = {}
output = {}
safe_count = 0
vul_count = 0
labels = []
fragment_contracts = []
dataframes_list = []

output_name = 'icse20'

vulnerability_stat = {
}
tool_stat = {}
tool_category_stat = {}
total_duration = 0
contract_vulnerabilities = {}

vulnerability_mapping = {}

tools = ['mythril', 'slither', 'osiris', 'smartcheck', 'manticore', 'maian', 'securify',
         'honeybadger']  # all tools analizer

target_vulnerability_integer_overflow = 'Integer Overflow'  # sum safe smart contract: 28953, sum vulnarable smart contract: 18445
target_vulnerability_reentrancy = 'Reentrancy'  # sum safe smart contract: 38423, sum vulnarable smart contract: 8975
target_vulnerability_transaction_order_dependence = 'Transaction order dependence'  # sum safe smart contract: 45380, sum vulnarable smart contract: 2018
target_vulnerability_timestamp_dependency = 'timestamp'  # sum safe smart contract: 45322 , sum vulnarable smart contract: 2076
target_vulnerability_callstack_depth_attack = 'Depth Attack'  # sum safe smart contract: 45380 , sum vulnarable smart contract: 2018
target_vulnerability_integer_underflow = 'Integer Underflow'  # sum safe smart contract: 43727 , sum vulnarable smart contract: 3671

target_vulner = target_vulnerability_reentrancy

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))

vulnerability_fd = open(os.path.join(ROOT, 'metadata', 'vulnerabilities.csv'), 'w', encoding='utf-8')

# PATH = f"{ROOT}\\contracts\\"  # main data set
PATH = f"{ROOT}\\contract\\"  # part of main data set
# PATH = f"{ROOT}\\contra\\"  # one smart contract
os.chdir(PATH)


# with open(os.path.join(ROOT, 'metadata', 'vulnerabilities_mapping.csv')) as fd:
#     header = fd.readline().strip().split(',')
#     line = fd.readline()
#     while line:
#         v = line.strip().split(',')
#         index = -1
#         if 'TRUE' in v:
#             index = v.index('TRUE')
#         elif 'MAYBE' in v:
#             index = v.index('MAYBE')
#         if index > -1:
#             vulnerability_mapping[v[1]] = header[index]
#         line = fd.readline()
#         print(f" Mapppppp {vulnerability_mapping}")
# categories = sorted(list(set(vulnerability_mapping.values())))
# categories.remove('Ignore')
# categories.remove('Other')
# categories.append('Other')

def is_sentence_in_text(sentence, text):
    sentence = sentence.lower()
    text = text.lower()
    text = re.sub(r'[^a-z ]', '', text)
    flg = sentence in text
    # print(flg)

    return flg


def refine_labels_for_reentrancy(df):
    for i, row in df[df['Vul'] == 1].iterrows():
        frag = row['Frag']

        # اگر خط خالی یا فقط شامل کامنت است، آن را ایمن فرض می‌کنیم
        if re.match(r'^\s*$', frag) or frag.strip().startswith('//'):
            df.at[i, 'Vul'] = 0  # خط خالی یا کامنت ایمن است

        # بررسی اینکه آیا فراخوانی خارجی واقعی و خطرناک است یا خیر
        elif re.search(r'\.call\(|\.send\(|\.transfer\(', frag):
            df.at[i, 'Vul'] = 1  # فراخوانی خارجی ممکن است همچنان آسیب‌پذیر باشد
        else:
            df.at[i, 'Vul'] = 0  # سایر خطوط در این محدوده ممکن است ایمن باشند


def getResultVulnarable(contract_name, target_vulnerability):
    total_duration = 0
    res = False
    lines = []
    for tool in tools:
        path_result = os.path.join(f"{ROOT}\\results\\", tool, output_name, contract_name, 'result.json')
        if not os.path.exists(path_result):
            continue
        with open(path_result, 'r', encoding='utf-8') as fd:
            data = None
            try:
                data = json.load(fd)
            except Exception as a:
                continue
            if tool not in duration_stat:
                duration_stat[tool] = 0
            if tool not in count:
                count[tool] = 0
            count[tool] += 1
            duration_stat[tool] += data['duration']
            total_duration += data['duration']

            if contract_name not in output:
                output[contract_name] = {
                    'tools': {},
                    'lines': set(),
                    'nb_vulnerabilities': 0
                }
            output[contract_name]['tools'][tool] = {
                'vulnerabilities': {},
                'categories': {}
            }
            if data['analysis'] is None:
                continue
            if tool == 'mythril':
                analysis = data['analysis']
                if analysis['issues'] is not None:
                    for result in analysis['issues']:
                        vulnerability = result['title'].strip()
                        if is_sentence_in_text(target_vulnerability, vulnerability):
                            res = True
                            lines.extend([result['lineno']])

            elif tool == 'oyente' or tool == 'osiris' or tool == 'honeybadger':
                for analysis in data['analysis']:
                    if analysis['errors'] is not None:
                        for result in analysis['errors']:
                            vulnerability = result['message'].strip()
                            if is_sentence_in_text(target_vulnerability, vulnerability):
                                res = True
                                lines.extend([result['line']])

            elif tool == 'manticore':
                for analysis in data['analysis']:
                    for result in analysis:
                        vulnerability = result['name'].strip()
                        if is_sentence_in_text(target_vulnerability, vulnerability):
                            res = True
                            lines.extend([result['line']])

            elif tool == 'maian':
                for vulnerability in data['analysis']:
                    if data['analysis'][vulnerability]:
                        if is_sentence_in_text(target_vulnerability, vulnerability):
                            res = True
                            # None lines

            elif tool == 'securify':
                for f in data['analysis']:
                    analysis = data['analysis'][f]['results']
                    for vulnerability in analysis:
                        for line in analysis[vulnerability]['violations']:
                            if is_sentence_in_text(target_vulnerability, vulnerability):
                                res = True
                                lines.extend([line + 1])

            elif tool == 'slither':
                analysis = data['analysis']
                for result in analysis:
                    vulnerability = result['check'].strip()
                    line = None
                    if 'source_mapping' in result['elements'][0] and len(
                            result['elements'][0]['source_mapping']['lines']) > 0:
                        line = result['elements'][0]['source_mapping']['lines']
                    if is_sentence_in_text(target_vulnerability, vulnerability):
                        if line is not None:
                            res = True
                            lines.extend(line)

            elif tool == 'smartcheck':
                analysis = data['analysis']
                for result in analysis:
                    vulnerability = result['name'].strip()
                    if is_sentence_in_text(target_vulnerability, vulnerability):
                        res = True
                        lines.extend([result['line']])

            elif tool == 'solhint':
                analysis = data['analysis']
                for result in analysis:
                    vulnerability = result['type'].strip()
                    if is_sentence_in_text(target_vulnerability, vulnerability):
                        res = True
                        lines.extend([int(result['line'])])

    return res, lines


def main(file_path, name, target_vulnerability):
    with open(file_path, encoding="utf8") as f:
        smartContractContent = f.read()
        isVulnarable, vulnerable_lines = getResultVulnarable(name, target_vulnerability)

        # get fragments
        fragments = PreProcessTools.get_fragments(smartContractContent)

        vulnerability_status = [1 if (i+1) in vulnerable_lines else 0 for i in range(len(fragments))]

        data_fr = pd.DataFrame({
            'Vul': vulnerability_status,
            'Frag': fragments
        })
        data_fr = data_fr[data_fr['Frag'].str.strip() != '']
        refine_labels_for_reentrancy(data_fr)

        dataframes_list.append(data_fr)


        # print(f"NAAAAAAAAAAAAAMMMMEEEEEEEEEEEEEEEE => {name}")
        # print(vulnerable_lines)
        # print(data_fr.to_string(index=False))
        # print(df.to_string())
        # print("__________________________________________________________________________________")

        # fragment_contracts.append(fragments)

        # isVal = 0
        # if (isVulnarable):
        #     isVal = 1

        # labels.append(isVal)
        # return isVulnarable

    combined_df = pd.concat(dataframes_list, ignore_index=True)
    combined_df = combined_df[~combined_df['Frag'].str.strip().isin(['', '}'])]

    X, Y, word2vec_model = tokenize_fragments(combined_df, save_path='tokenized_data.pkl')

    # بررسی ابعاد داده‌ها و مشاهده نمونه‌ای از برچسب‌ها
    print("Shape of X:", X.shape)
    print("Shape of Y:", Y.shape)
    print("First 5 labels in Y:", Y[:5])


def get_word2vec_embeddingss(text, word2vec_model):
    embeddings = [word2vec_model.wv[word] for word in text if word in word2vec_model.wv]
    return embeddings


def tokenize_fragmentss(combined_df):
    # tokenizer = Tokenizer()
    # tokenizer.fit_on_texts(combined_df['Frag'])  # 'Frag' ستونی است که شامل خطوط کد است
    #
    # # تبدیل خطوط کد به توالی اعداد
    # sequences = tokenizer.texts_to_sequences(combined_df['Frag'])
    # max_length = max(len(seq) for seq in sequences)  # تعیین طول بیشینه توالی
    #
    # # پد کردن یا برش توالی‌ها به طول ثابت 100
    # X = pad_sequences(sequences, maxlen=100, padding='post', truncating='post')
    # y = combined_df['Vul'].values  # لیبل‌ها
    #
    # for i in range(5):  # 5 نمونه اول
    #     print("Original:", combined_df['Frag'].iloc[i])
    #     print("Tokenized:", sequences[i])
    #     print()

    # ایجاد مجموعه داده برای Word2Vec
    tokenized_texts = [line.split() for line in combined_df['Frag']]  # هر خط را به لیست کلمات تبدیل کنید

    # آموزش مدل Word2Vec
    word2vec_model = Word2Vec(sentences=tokenized_texts, vector_size=200, window=5, min_count=1, workers=4)

    # تبدیل همه خطوط کد به بردارهای Word2Vec
    X = [get_word2vec_embeddingss(line.split(), word2vec_model) for line in combined_df['Frag']]

    # پد کردن توالی‌ها
    X = pad_sequences([np.array(seq).mean(axis=0) for seq in X if len(seq) > 0], maxlen=200, dtype='float32', padding='post')
    Y = combined_df['Vul'].values

    # similarity = word2vec_model.wv.similarity('transfer', 'send')
    # print("Similarity between 'call' and 'send':", similarity)

    sample_embedding = get_word2vec_embeddingss(tokenized_texts[0], word2vec_model)
    if len(sample_embedding) > 0:
        mean_embedding = np.array(sample_embedding).mean(axis=0)
        print("Mean embedding shape:", mean_embedding.shape)


def get_word2vec_embeddings(text, word2vec_model):
    embeddings = [word2vec_model.wv[word] for word in text if word in word2vec_model.wv]
    return embeddings


def tokenize_fragments(combined_df, save_path='tokenized_data.pkl'):
    try:
        # بررسی اینکه فایل ذخیره‌شده وجود دارد یا نه
        with open(save_path, 'rb') as file:
            data = pickle.load(file)
            X, Y, word2vec_model = data['X'], data['Y'], data['word2vec_model']
            print("Loaded tokenized data from saved file.")
    except FileNotFoundError:
        print("No saved file found. Generating tokenized data...")
        # لیست توکن‌های هر خط از کد
        tokenized_texts = [line.split() for line in combined_df['Frag']]

        # آموزش مدل Word2Vec
        word2vec_model = Word2Vec(sentences=tokenized_texts, vector_size=200, window=5, min_count=1, workers=4)

        # تبدیل خطوط کد به بردارهای word2vec و محاسبه میانگین
        X = [get_word2vec_embeddings(line.split(), word2vec_model) for line in combined_df['Frag']]
        X = [np.array(seq).mean(axis=0) if len(seq) > 0 else np.zeros(word2vec_model.vector_size) for seq in X]

        # پد کردن توالی‌ها به طول ثابت
        X = pad_sequences([X], maxlen=200, dtype='float32', padding='post')
        Y = combined_df['Vul'].values

        # بررسی نتایج نمونه
        # sample_embedding = get_word2vec_embeddings(tokenized_texts[0], word2vec_model)
        # if len(sample_embedding) > 0:
        #     mean_embedding = np.array(sample_embedding).mean(axis=0)
        #     print("Mean embedding shape:", mean_embedding.shape)

        # print("Word2Vec vocabulary:", list(word2vec_model.wv.key_to_index.keys())[:10])  # 10 کلمه اول واژه‌نامه

        # if 'call' in word2vec_model.wv:
        #     print("Embedding for 'send':", word2vec_model.wv['send'])
        #
        # sample_embedding = get_word2vec_embeddings(tokenized_texts[0], word2vec_model)
        # if len(sample_embedding) > 0:
        #     mean_embedding = np.array(sample_embedding).mean(axis=0)
        #     print("Mean embedding shape for one line:", mean_embedding.shape)
        #     print("Mean embedding vector:", mean_embedding)  # چاپ بردار میانگین
        #
        # print("Shape of padded X:", X.shape)  # باید (تعداد نمونه‌ها، 200، 200) باشد
        # print("First sequence after padding:", X[0])  # مشاهده اولین توالی پد شده
        #
        # print("Shape of Y:", Y.shape)  # مطمئن شوید که تعداد ردیف‌های Y با X مطابقت دارد
        # print("Sample labels:", Y[:5])  # مشاهده چند نمونه از برچسب‌ها
        # print("Number of non-vulnerable (0) samples:", sum(Y == 0))
        # print("Number of vulnerable (1) samples:", sum(Y == 1))
        # print("Value counts in 'Vul' column:")
        # print(combined_df['Vul'].value_counts())



        # plt.figure(figsize=(10, 5))
        # sns.countplot(data=combined_df, x='Vul')
        # plt.title("Distribution of Vulnerability Labels")
        # plt.show()

        with open(save_path, 'wb') as file:
            pickle.dump({'X': X, 'Y': Y, 'word2vec_model': word2vec_model}, file)
            print("Tokenized data saved to file.")

    return X, Y, word2vec_model

if __name__ == "__main__":
    for file in os.listdir():
        # Check whether file is in text format or not
        if file.endswith(".sol"):
            file_path = f"{PATH}\{file}"
            name = file.replace(".sol", "")

            # set type vulnerability
            # target_vulner = target_vulnerability_integer_overflow

            if (main(file_path, name, target_vulner)):
                vul_count += 1
            else:
                safe_count += 1
