# AUTOGENERATED! DO NOT EDIT! File to edit: tab_ae.ipynb (unless otherwise specified).

__all__ = ['ReadTabBatchIdentity', 'TabularPandasIdentity', 'TabDataLoaderIdentity', 'RecreatedLoss', 'BatchSwapNoise',
           'TabularAE']

# Cell
from fastai.tabular.all import *

# Cell
class ReadTabBatchIdentity(ItemTransform):
    "Read a batch of data and return the inputs as both `x` and `y`"
    def __init__(self, to): self.to = to

    def encodes(self, to):
        if not to.with_cont: res = (tensor(to.cats).long(),) + (tensor(to.cats).long(),)
        else: res = (tensor(to.cats).long(),tensor(to.conts).float()) + (tensor(to.cats).long(), tensor(to.conts).float())
        if to.device is not None: res = to_device(res, to.device)
        return res

class TabularPandasIdentity(TabularPandas): pass

# Cell

@delegates()
class TabDataLoaderIdentity(TabDataLoader):
    "A transformed `DataLoader` for AutoEncoder problems with Tabular data"
    do_item = noops
    def __init__(self, dataset, bs=16, shuffle=False, after_batch=None, num_workers=0, **kwargs):
        if after_batch is None: after_batch = L(TransformBlock().batch_tfms)+ReadTabBatchIdentity(dataset)
        super().__init__(dataset, bs=bs, shuffle=shuffle, after_batch=after_batch, num_workers=num_workers, **kwargs)

    def create_batch(self, b): return self.dataset.iloc[b]

# Cell
class RecreatedLoss(Module):
    "Measures how well we have created the original tabular inputs"
    def __init__(self, cat_dict):
        ce = CrossEntropyLossFlat(reduction='sum')
        mse = MSELossFlat(reduction='sum')
        #store_attr('cat_dict,ce,mse')
        self.cat_dict = cat_dict
        self.ce = ce
        self.mse = mse

    def forward(self, preds, cat_targs, cont_targs):
        cats, conts = preds
        tot_ce, pos = cats.new([0]), 0
        for i, (k,v) in enumerate(self.cat_dict.items()):
            tot_ce += self.ce(cats[:, pos:pos+v], cat_targs[:,i])
            pos += v

        norm_cats = cats.new([len(self.cat_dict)])
        norm_conts = conts.new([conts.size(1)])
        cat_loss = tot_ce/norm_cats
        cont_loss = self.mse(conts, cont_targs)/norm_conts
        total = cat_loss+cont_loss

        return total / cats.size(0)

# Cell
class BatchSwapNoise(Module):
    "Swap Noise Module"
    def __init__(self, p): #store_attr()
        self.p = p


    def forward(self, x):
        if self.training:
            mask = torch.rand(x.size()) > (1 - self.p)
            l1 = torch.floor(torch.rand(x.size()) * x.size(0)).type(torch.LongTensor)
            l2 = (mask.type(torch.LongTensor) * x.size(1))
            res = (l1 * l2).view(-1)
            idx = torch.arange(x.nelement()) + res
            idx[idx>=x.nelement()] = idx[idx>=x.nelement()]-x.nelement()
            return x.flatten()[idx].view(x.size())
        else:
            return x

# Cell
class TabularAE(TabularModel):
    "A simple AutoEncoder model"
    def __init__(self, emb_szs, n_cont, hidden_size, cats, low, high, ps=0.2, embed_p=0.01, bswap=None):
        super().__init__(emb_szs, n_cont, layers=[1024, 512, 256], out_sz=hidden_size, embed_p=embed_p)

        self.bswap = bswap
        self.cats = cats
        self.activation_cats = sum([v for k,v in cats.items()])

        self.layers = nn.Sequential(*L(self.layers.children())[:-1] + nn.Sequential(LinBnDrop(256, hidden_size, p=ps, act=Mish())))

        if(bswap != None): self.noise = BatchSwapNoise(bswap)
        self.decoder = nn.Sequential(
            LinBnDrop(hidden_size, 256, p=ps, act=Mish()),
            LinBnDrop(256, 512, p=ps, act=Mish()),
            LinBnDrop(512, 1024, p=ps, act=Mish())
        )

        self.decoder_cont = nn.Sequential(
            LinBnDrop(1024, n_cont, p=ps, bn=False, act=None),
            SigmoidRange(low=low, high=high)
        )

        self.decoder_cat = LinBnDrop(1024, self.activation_cats, p=ps, bn=False, act=None)

    def forward(self, x_cat, x_cont=None, encode=False):
        if(self.bswap != None):
            x_cat = self.noise(x_cat)
            x_cont = self.noise(x_cont)
        encoded = super().forward(x_cat, x_cont)
        if encode: return encoded # return the representation
        decoded_trunk = self.decoder(encoded)
        decoded_cats = self.decoder_cat(decoded_trunk)
        decoded_conts = self.decoder_cont(decoded_trunk)
        return decoded_cats, decoded_conts