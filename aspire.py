#!/usr/bin/env python
'''Convert speech audio to text output, with alignments, using Kaldi.'''

import subprocess, shlex, sys
import os
from filegen import filegen
from id2phone import id2phone
from id2word import id2word
from ctm2tg import ctm2tg

srcpath = "/Users/darkapex/git/kaldi/src/"
mfcc_config = "conf/mfcc_hires.conf"
lang_dir = "data/lang_pp_test"
data_dir = "data/alignme"
ivec_extractor = "exp/tdnn_7b_chain_online/ivector_extractor"
phones = "exp/tdnn_7b_chain_online/phones.txt"
words = "exp/tdnn_7b_chain_online/graph_pp/words.txt"
model = "exp/tdnn_7b_chain_online/final.mdl"
graph = "exp/tdnn_7b_chain_online/graph_pp/HCLG.fst"

def compute_mfcc(config, data_dir):
    '''Compute MFCC Features, and store in data_dir/feats.scp'''
    cmd = srcpath + "featbin/compute-mfcc-feats --config=%s scp:%s ark,scp:%s/feats.ark,%s/feats.scp"
    cmd = cmd % (config, os.path.join(data_dir, "wav.scp"), data_dir, data_dir)
    print "Computing MFCC features...",
    proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    assert proc.returncode == 0
    print "done"

def extract_ivectors(extractor, lang_dir, data_dir):
    '''Extract IVector features and store in data_dir/ivectors'''
    cmd = "steps/online/nnet2/extract_ivectors.sh --nj 1 %s %s %s %s/ivectors"
    cmd = cmd % (data_dir, lang_dir, extractor, data_dir)
    print "Extracting Ivectors...",
    proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    assert proc.returncode == 0
    print "done"

def decode_and_align(words, model, graph, data_dir):
    '''Decode-and-align wavfiles.
    
    text output: data_dir/text
    alignments: data_dir/align.ali
    
    Args:
        words -- words.txt file containing word_id and word mappings
        model -- pre-trained nnet3 kaldi model (tested with aspire)
        graph -- compiled FST graph for the grammar
        data_dir -- path to a directory where decoding/alignment output should be stored
    '''
    cmd = srcpath + '''nnet3bin/nnet3-latgen-faster --print-args=0\
    --online-ivectors=scp:%s/ivectors/ivector_online.scp \
    --online-ivector-period=10 \
    --frame-subsampling-factor=3 \
    --max-active=7000 \
    --beam=15.0 \
    --lattice-beam=6.0 \
    --acoustic-scale=1.0 \
    --word-symbol-table=%s\
    %s %s \
    ark:%s/feats.ark \
    ark,t:%s/lattices.ark \
    ark:/dev/null \
    ark:%s/align.ali'''
    cmd = cmd % (data_dir, words, model, graph, data_dir, data_dir, data_dir)
    print "Decoding and aligning..."
    proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr = proc.communicate()[1]
    proc.wait()
    assert proc.returncode == 0
    f = open(os.path.join(data_dir, "text"), 'w')
    for line in stderr.splitlines():
        if not line.startswith('LOG'):
            print(line)
            f.write(line + '\n')
    print "Alignments stored in " + os.path.join(data_dir, "align.ali")

def phoneme_ctm(model, data_dir):
    '''Convert ark phone alignments file to human readable CTM.'''
    cmd = srcpath + "bin/ali-to-phones --frame-shift=0.03 --ctm-output %s ark:%s/align.ali %s/phonelvl.ctm"
    cmd = cmd % (model, data_dir, data_dir)
    print "Getting phoneme level ctm file...",
    proc = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    assert proc.returncode == 0
    id2phone(phones, os.path.join(data_dir, "phonelvl.ctm"))
    print "stored in " + os.path.join(data_dir, "phonelvl.ctm")

def word_ctm(lang_dir, model, data_dir):
    '''Convert ark word alignments file to human readable CTM.'''
    cmd = '''%s/latbin/lattice-align-words-lexicon %s/phones/align_lexicon.int %s ark:%s/lattices.ark ark:- | \
      %s/latbin/lattice-1best ark:- ark:- | \
      %s/latbin/nbest-to-ctm --frame-shift=0.03 ark:- %s/wordlvl.ctm'''
    cmd = cmd % (srcpath, lang_dir, model, data_dir, srcpath, srcpath, data_dir)
    print "Getting word level ctm file...",
    # TODO: Pipe using python, not shell
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    assert proc.returncode == 0
    id2word(words, os.path.join(data_dir, "wordlvl.ctm"))
    print "stored in " + os.path.join(data_dir, "wordlvl.ctm")

def run_praat(wav_dir, data_dir):
    '''Run Praat to display TextGrid files alongside the wav input.'''
    cmd = '''praat --open %s/* %s/*''' % (wav_dir, os.path.join(data_dir, 'tg'))
    print "Running Praat"
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    assert proc.returncode == 0
    print "Exiting.."

def main():
    global data_dir
    if (len(sys.argv) < 2):
        print "Usage: %s <wavdir> [<datadir>]" % (sys.argv[0])
        exit(1)
    wav_dir = sys.argv[1]
    if (len(sys.argv) == 3):
        data_dir = sys.argv[2]
    print "Generating spk2utt, utt2spk, wav.scp...",
    filegen(wav_dir, data_dir)
    print "done"
    compute_mfcc(mfcc_config, data_dir)
    extract_ivectors(ivec_extractor, lang_dir, data_dir)
    decode_and_align(words, model, graph, data_dir)
    phoneme_ctm(model, data_dir)
    word_ctm(lang_dir, model, data_dir)
    ctm2tg(wav_dir, data_dir)
    disp = raw_input("Display alignments using Praat right now? (y/n): ")
    disp = disp.lower()
    if (disp == 'y' or disp == 'yes'):
        run_praat(wav_dir, data_dir)

if __name__ == '__main__':
    main()
