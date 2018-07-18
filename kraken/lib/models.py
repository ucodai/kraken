"""
kraken.lib.models
~~~~~~~~~~~~~~~~~

Wrapper around TorchVGSLModel including a variety of forward pass helpers for
sequence classification.
"""
from os.path import expandvars, expanduser, abspath

import kraken.lib.lineest
import kraken.lib.ctc_decoder

from kraken.lib.vgsl import TorchVGSLModel
from kraken.lib.exceptions import KrakenInvalidModelException, KrakenInputException

__all__ = ['TorchSeqRecognizer', 'load_any']

import logging

logger = logging.getLogger(__name__)


class TorchSeqRecognizer(object):
    """
    A class wrapping a TorchVGSLModel with a more comfortable recognition interface.
    """
    def __init__(self, nn, decoder=kraken.lib.ctc_decoder.greedy_decoder, train=False, device='cpu'):
        """
        Constructs a sequence recognizer from a VGSL model and a decoder.

        Args:
            nn (kraken.lib.vgsl.TorchVGSLModel): neural network used for recognition
            decoder (func): Decoder function used for mapping softmax
                            activations to labels and positions
            train (bool): Enables or disables gradient calculation
            device (torch.Device): Device to run model on
        """
        self.nn = nn
        if train:
            self.nn.train()
        else:
            self.nn.eval()
        self.codec = self.nn.codec
        self.decoder = decoder
        self.train = train
        self.device = device
        self.nn.to(device)

    def to(self, device):
        """
        Moves model to device and automatically loads input tensors onto it.
        """
        self.device = device
        self.nn.to(device)

    def forward(self, line):
        """
        Performs a forward pass on a torch tensor of a line with shape (C, H, W)
        and returns a numpy array (W, C).
        """
        # make CHW -> 1CHW
        line = line.to(self.device)
        line = line.unsqueeze(0)
        o = self.nn.nn(line)
        if o.size(2) != 1:
            raise KrakenInputException('Expected dimension 3 to be 1, actual {}'.format(o.size()))
        self.outputs = o.data.squeeze().numpy()
        return self.outputs

    def predict(self, line):
        """
        Performs a forward pass on a torch tensor of a line with shape (C, H, W)
        and returns the decoding as a list of tuples (string, start, end,
        confidence).
        """
        o = self.forward(line)
        locs = self.decoder(o)
        return self.codec.decode(locs)

    def predict_string(self, line):
        """
        Performs a forward pass on a torch tensor of a line with shape (C, H, W)
        and returns a string of the results.
        """
        o = self.forward(line)
        locs = self.decoder(o)
        decoding = self.codec.decode(locs)
        return ''.join(x[0] for x in decoding)

    def predict_labels(self, line):
        """
        Performs a forward pass on a torch tensor of a line with shape (C, H, W)
        and returns a list of tuples (class, start, end, max). Max is the
        maximum value of the softmax layer in the region.
        """
        o = self.forward(line)
        return self.decoder(o)


def load_any(fname, train=False):
    """
    Loads anything that was, is, and will be a valid ocropus model and
    instantiates a shiny new kraken.lib.lstm.SeqRecognizer from the RNN
    configuration in the file.

    Currently it recognizes the following kinds of models:
        * pyrnn models containing BIDILSTMs
        * protobuf models containing converted python BIDILSTMs
        * protobuf models containing CLSTM networks

    Additionally an attribute 'kind' will be added to the SeqRecognizer
    containing a string representation of the source kind. Current known values
    are:
        * pyrnn for pickled BIDILSTMs
        * clstm for protobuf models generated by clstm

    Args:
        fname (unicode): Path to the model
        train (bool): Enables gradient calculation and dropout layers in model.

    Returns:
        A kraken.lib.models.TorchSeqRecognizer object.
    """
    nn = None
    kind = ''
    fname = abspath(expandvars(expanduser(fname)))
    logger.info(u'Loading model from {}'.format(fname))
    try:
        nn = TorchVGSLModel.load_model(str(fname))
        kind = 'vgsl'
    except Exception:
        try:
            nn = TorchVGSLModel.load_clstm_model(fname)
            kind = 'clstm'
        except Exception:
            nn = TorchVGSLModel.load_pronn_model(fname)
            kind = 'pronn'
        try:
            nn = TorchVGSLModel.load_pyrnn_model(fname)
            kind = 'pyrnn'
        except Exception:
            pass
    if not nn:
        raise KrakenInvalidModelException('File {} not loadable by any parser.'.format(fname))
    seq = TorchSeqRecognizer(nn, train=train)
    seq.kind = kind
    return seq
